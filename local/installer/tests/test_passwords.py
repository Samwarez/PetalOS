"""Meaningful weak-pattern, creation-policy and meter-failure regressions."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petal_installer import passwords
from petal_installer.bridge import collect_credentials
from petal_installer import InstallerError


class PasswordTests(unittest.TestCase):
    def test_dictionary_repetition_and_keyboard_patterns_stay_weak_despite_length(self):
        for value in ('a' * 24, 'passwordpasswordpassword', 'qwertyuiopqwertyuiopqwertyuiop',
                      '123456789012345678901234', 'Password1!Password1!Password1!'):
            with self.subTest(pattern=value):
                result = passwords.strength(value, 'private')
                self.assertLessEqual(result['score'], 1)
                self.assertIn('minimum met', result['text'])

    def test_unpredictable_test_sample_scores_above_common_patterns(self):
        result = passwords.strength('m8T!r4W#p9L$k2V%z7N@x6Q&', 'private')
        self.assertGreaterEqual(result['score'], 3)
        self.assertNotIn('m8T', result['text'])

    def test_length_compliance_does_not_claim_strength(self):
        result = passwords.strength('a' * 24, 'private')
        self.assertIn('Very weak', result['text'])
        self.assertIn('minimum met', result['text'])
        self.assertIn('14/15', passwords.strength('a' * 14, 'system')['text'])
        self.assertEqual(passwords.strength('', 'private')['score'], 0)

    def test_missing_library_unicode_and_invalid_estimate_never_claim_strength(self):
        for error in (OSError('unavailable'), AttributeError('missing symbol')):
            with patch.object(passwords, '_matcher', side_effect=error):
                self.assertIn('unavailable', passwords.strength('a' * 24, 'private')['text'])
        with patch.object(passwords, '_matcher') as matcher:
            self.assertIn('unavailable', passwords.strength('🌸' * 24, 'private')['text'])
            matcher.assert_not_called()
        for value in (float('nan'), float('inf'), -1):
            with patch.object(passwords, '_matcher', return_value=lambda *_: value):
                self.assertEqual(passwords.strength('a' * 24, 'private')['score'], 0)

    def test_matching_work_is_bounded_without_caching_passwords(self):
        with patch.object(passwords, '_matcher') as matcher:
            matcher.return_value.return_value = 50
            passwords.strength('x' * 512, 'private')
            self.assertEqual(len(matcher.return_value.call_args.args[0]), 128)
        self.assertFalse(hasattr(passwords.strength, 'cache_info'))

    def test_cli_explains_role_minimums_and_confirms_before_backend(self):
        values = ('s' * 15, 'p' * 24, 'a' * 15)
        with patch('petal_installer.bridge.getpass.getpass', side_effect=[v for v in values for _ in range(2)]) as prompt:
            self.assertEqual(collect_credentials('install', encryption='paranoid')['private'], values[1])
            self.assertIn('at least 15', prompt.call_args_list[0].args[0])
            self.assertIn('at least 24', prompt.call_args_list[2].args[0])
        with patch('petal_installer.bridge.getpass.getpass', side_effect=['s' * 15, 'different']):
            with self.assertRaises(InstallerError):collect_credentials('install')


if __name__ == '__main__':unittest.main()
