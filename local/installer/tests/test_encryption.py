from pathlib import Path
import copy
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petal_installer import InstallerError, encryption, engine, layout2
from test_installer import bundle, disk
from petal_installer.plans import make_plan


class EncryptionTests(unittest.TestCase):
    def test_tiers_have_same_data_cipher_and_ordered_password_costs(self):
        values = list(encryption.PROFILES.values())
        self.assertEqual(list(encryption.PROFILES), ['fast', 'balanced', 'paranoid'])
        self.assertTrue(all(p['cipher'] == 'aes-xts-plain64' and p['key_bits'] == 512 and p['pbkdf'] == 'argon2id' for p in values))
        self.assertEqual([p['target_unlock_ms'] for p in values], [1000, 2000, 5000])
        self.assertLess(values[0]['memory_kib'], values[1]['minimum_memory_kib'])
        self.assertLess(values[1]['memory_kib'], values[2]['minimum_memory_kib'])

    def test_calibration_keeps_headroom_and_checks_the_cpu_budget(self):
        hardware = {'total_kib': 4 * 1024**2, 'available_kib': 3 * 1024**2, 'cpus': 2}
        value = encryption.budget('paranoid', hardware)
        self.assertEqual(value['memory_kib'], hardware['available_kib'] // 2)
        self.assertEqual(value['parallel'], 2)
        with self.assertRaises(InstallerError):encryption.budget('paranoid', dict(hardware, available_kib=512*1024))

    def test_real_benchmark_parameters_are_checked_not_assumed(self):
        hardware = {'total_kib': 8 * 1024**2, 'available_kib': 6 * 1024**2, 'cpus': 4}
        command = Mock(return_value=b'argon2id 4 iterations, 1048576 memory, 4 parallel threads (CPUs) for 512-bit key (requested 5000 ms time)\n')
        value = encryption.calibrate('paranoid', hardware=hardware, command=command)
        self.assertEqual(value['memory_kib'], 1048576)
        for output in (b'unrecognized benchmark', b'argon2id 4 iterations, 65536 memory, 4 parallel threads',
                       b'argon2id 1 iterations, 1048576 memory, 4 parallel threads',
                       b'argon2id 4 iterations, 1048576 memory, 8 parallel threads'):
            with self.assertRaises(InstallerError):encryption.calibrate('paranoid', hardware=hardware, command=Mock(return_value=output))

    def test_calibrated_format_and_readback_cannot_silently_weaken(self):
        value = {'profile': 'balanced', 'iterations': 7, 'memory_kib': 524288, 'parallel': 2, 'target_unlock_ms': 2000}
        args = layout2.encryption_arguments('/dev/mock', 'os', '11111111-1111-1111-1111-111111111111', calibration=value)
        self.assertIn('--pbkdf-force-iterations', args)
        self.assertNotIn('--iter-time', args)
        metadata = {'segments': {'0': {'encryption': 'aes-xts-plain64'}}, 'keyslots': {'0': {
            'key_size': 64, 'kdf': {'type': 'argon2id', 'time': 7, 'memory': 524288, 'cpus': 2}}}}
        encryption.verify_header(metadata, 'balanced', value)
        for field, wrong in [('type', 'pbkdf2'), ('memory', 65536), ('time', 4), ('cpus', 1)]:
            changed = copy.deepcopy(metadata);changed['keyslots']['0']['kdf'][field] = wrong
            with self.assertRaises(InstallerError):encryption.verify_header(changed, 'balanced', value)

    def test_slow_cpu_extends_unlock_work_instead_of_weakening_the_tier(self):
        hardware = {'total_kib': 8 * 1024**2, 'available_kib': 6 * 1024**2, 'cpus': 4}
        command = Mock(side_effect=[b'argon2id 4 iterations, 131072 memory, 4 parallel threads',
                                    b'argon2id 4 iterations, 262144 memory, 4 parallel threads'])
        result = encryption.calibrate('balanced', hardware=hardware, command=command)
        self.assertEqual(result['memory_kib'], 262144)
        self.assertEqual(result['target_unlock_ms'], 4000)
        self.assertEqual(command.call_count, 2)

    def test_paranoid_enforces_long_distinct_new_credentials_but_reads_legacy(self):
        values = {'system': 's' * 32, 'private': 'p' * 32, 'administrator': 'a' * 32}
        engine.credentials_checked(values, 'install', encryption='paranoid')
        with self.assertRaises(InstallerError):engine.credentials_checked(dict(values, private='p' * 31), 'install', encryption='paranoid')
        with self.assertRaises(InstallerError):engine.credentials_checked(dict(values, private=values['system']), 'install', encryption='paranoid')
        # Existing keys are verified using their existing credential, never silently rotated.
        engine.credentials_checked({'system': 'old'}, 'update')

    def test_failed_calibration_never_opens_or_erases_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = bundle(Path(temporary) / 'build');record = disk()
            plan = make_plan('install', record, bundle=source)
            from petal_installer.bridge import request_from_plan
            request = request_from_plan(plan, source)
            with patch.object(engine.os, 'geteuid', return_value=0), patch.object(engine.resource, 'setrlimit'), \
                 patch.object(engine.ctypes, 'CDLL', return_value=Mock(prctl=Mock(return_value=0))), \
                 patch.object(engine.linux, 'choose', return_value=record), patch.object(engine, 'validate_os'), \
                 patch.object(engine, 'calibrate', side_effect=InstallerError('Insufficient memory.')), patch.object(engine, 'Target') as target:
                with self.assertRaises(InstallerError):engine.execute(request, {'system': 'system-test-unique', 'private': 'private-test-unique', 'administrator': 'admin-test-unique'})
                target.assert_not_called()


if __name__ == '__main__':unittest.main()
