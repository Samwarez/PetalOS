#!/usr/bin/python3
"""Bounded QEMU metadata audit; no private contents or credential databases."""
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess


def run(command, timeout=15):
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def main():
    assert os.geteuid() == 0
    assert run(['systemd-detect-virt']).stdout.strip() in ('qemu', 'kvm')
    account = pwd.getpwuid(1000)
    assert account.pw_name == 'Petal'
    result = {}
    result['listeners'] = run(['ss', '-lntup']).stdout.splitlines()
    result['failed_units'] = run(['systemctl', '--failed', '--no-legend']).stdout.splitlines()
    result['enabled_units'] = run(['systemctl', 'list-unit-files', '--state=enabled', '--no-legend']).stdout.splitlines()
    result['root_login_locked'] = run(['passwd', '-S', 'root']).stdout.split()[1] in ('L', 'LK')
    result['active_profiles'] = json.loads(run(['/usr/sbin/aa-status', '--json']).stdout)['profiles']
    result['mounts'] = json.loads(run(['findmnt', '-J', '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS']).stdout)
    result['sudo_policy_valid'] = run(['/usr/sbin/visudo', '-c']).returncode == 0
    result['private_directory_mode'] = oct(Path('/mnt/private').stat().st_mode & 0o777)
    result['runtime_vpn_owner_mode'] = str(Path('/etc/wireguard/wg0.conf').stat().st_uid) + ':' + oct(Path('/etc/wireguard/wg0.conf').stat().st_mode & 0o777)
    result['network_directory_mode'] = oct(Path('/mnt/private/Network').stat().st_mode & 0o777)
    result['system_key_metadata_safe'] = None
    # The already-mounted encrypted live medium exposes metadata only. Never
    # open the key, list personal files, or attach a disk on the host.
    medium = Path('/run/live/medium')
    directory = medium / '.portable-keys'
    key = directory / 'data.key'
    if directory.exists() and key.exists():
        di, ki = directory.lstat(), key.lstat()
        result['system_key_metadata_safe'] = (stat.S_ISDIR(di.st_mode) and di.st_uid == 0 and di.st_mode & 0o777 == 0o700 and stat.S_ISREG(ki.st_mode) and ki.st_uid == 0 and ki.st_mode & 0o777 == 0o600 and ki.st_nlink == 1)
    else:
        # toram copies only live media into RAM. Inspect the encrypted SYSTEM
        # through the existing strict guest-side read-only mount helper.
        import sys
        sys.path.insert(0, '/usr/local/lib/portable')
        from account_auth import system_filesystem
        with system_filesystem() as system:
            di = (system / '.portable-keys').lstat()
            ki = (system / '.portable-keys/data.key').lstat()
            result['system_key_metadata_safe'] = (stat.S_ISDIR(di.st_mode) and di.st_uid == 0 and di.st_mode & 0o777 == 0o700 and stat.S_ISREG(ki.st_mode) and ki.st_uid == 0 and ki.st_mode & 0o777 == 0o600 and ki.st_nlink == 1)
    result['raw_encrypted_disks_readable_by_petal'] = {}
    for name in ('portable_system', 'portable_data'):
        dev = Path('/dev/mapper') / name
        check = run(['/usr/sbin/runuser', '-u', 'Petal', '--', '/usr/bin/test', '-r', str(dev)])
        result['raw_encrypted_disks_readable_by_petal'][name] = check.returncode == 0
        info = dev.stat()
        slaves = list(Path('/sys/dev/block/' + str(os.major(info.st_rdev)) + ':' + str(os.minor(info.st_rdev)) + '/slaves').iterdir())
        assert len(slaves) == 1
        backing = '/dev/' + slaves[0].name
        metadata = json.loads(run(['/usr/sbin/cryptsetup', 'luksDump', '--dump-json-metadata', backing]).stdout)
        result[name + '_encryption'] = {
            'segments': [{'type': x.get('type'), 'encryption': x.get('encryption'), 'sector_size': x.get('sector_size')} for x in metadata.get('segments', {}).values()],
            'keyslots': [{'type': x.get('type'), 'key_size': x.get('key_size'), 'kdf_type': x.get('kdf', {}).get('type'), 'kdf_memory': x.get('kdf', {}).get('memory'), 'kdf_time': x.get('kdf', {}).get('time'), 'kdf_iterations': x.get('kdf', {}).get('iterations')} for x in metadata.get('keyslots', {}).values()],
        }
    result['setuid_setgid_commands'] = run(['find', '/usr/bin', '/usr/sbin', '/usr/lib', '-xdev', '-type', 'f', '-perm', '/6000', '-printf', '%p %m\n'], 30).stdout.splitlines()
    result['file_capabilities'] = run(['/usr/sbin/getcap', '-r', '/usr/bin', '/usr/sbin', '/usr/lib'], 30).stdout.splitlines()
    result['polkit_rules'] = {}
    for directory in ('/etc/polkit-1/rules.d', '/usr/share/polkit-1/rules.d'):
        for rule in sorted(Path(directory).glob('*.rules')):
            # Package-installed access policy, never account databases.
            if rule.stat().st_size < 65536:
                result['polkit_rules'][str(rule)] = rule.read_text()
    result['machine_id_in_base'] = False
    layers = Path('/run/live/rootfs')
    for layer in layers.glob('filesystem.squashfs'):
        machine_id = layer / 'etc/machine-id'
        result['machine_id_in_base'] = machine_id.exists() and bool(machine_id.read_text().strip())
    result['kernel_security'] = {name: Path('/proc/sys/' + name).read_text().strip() for name in ('kernel/kptr_restrict', 'kernel/dmesg_restrict', 'kernel/yama/ptrace_scope', 'kernel/unprivileged_bpf_disabled', 'kernel/perf_event_paranoid', 'kernel/kexec_load_disabled') if Path('/proc/sys/' + name).is_file()}
    result['bluetooth_controllers_present'] = any(Path('/sys/class/bluetooth').glob('hci*'))
    result['bluetooth_powered'] = None
    if result['bluetooth_controllers_present']:
        try:
            result['bluetooth_powered'] = 'Powered: yes' in run(['bluetoothctl', 'show'], 3).stdout
        except subprocess.TimeoutExpired:
            result['bluetooth_powered'] = 'query timed out'
    result['x11_tcp_listener'] = any(':6000 ' in line for line in result['listeners'])
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
