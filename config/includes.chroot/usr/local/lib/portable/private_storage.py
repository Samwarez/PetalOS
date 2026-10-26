"""Fixed encrypted-storage controller; backend operations never emit secrets."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time

ROOT = Path('/run/portable-storage')
PRIVATE = Path('/mnt/private')
DESKTOP_TRASH = Path('/home/Petal/.local/share/Trash')
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'LC_ALL': 'C.UTF-8'}


class StorageOperationError(RuntimeError):
    def __init__(self, returncode):
        super().__init__('Storage operation failed.')
        self.returncode = returncode


class PassphraseRejected(StorageOperationError):
    """A LUKS verifier explicitly rejected the supplied passphrase."""


def command(arguments, *, password=None, timeout=5):
    result = subprocess.run(arguments, input=password, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, env=ENV, timeout=timeout)
    if result.returncode:
        # Exit 2 can also mean a permissions failure. Retry only the specific
        # C-locale LUKS rejection, never device, mount or general access errors.
        rejected = (password is not None and arguments[:2] == ['/usr/sbin/cryptsetup', 'open']
                    and result.returncode == 2
                    and b'No key available with this passphrase.' in result.stderr.splitlines())
        if rejected:
            raise PassphraseRejected(result.returncode)
        raise StorageOperationError(result.returncode)


def directory():
    assert os.geteuid() == 0
    assert not ROOT.is_symlink()
    ROOT.mkdir(mode=0o700, exist_ok=True)
    info = ROOT.stat()
    assert info.st_uid == 0 and stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o077
    return ROOT


@contextmanager
def operation(shared=False):
    directory()
    fd = os.open(ROOT / 'operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+b') as lock:
        info = os.fstat(lock.fileno())
        assert info.st_uid == 0 and stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077
        fcntl.flock(lock, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        yield


def remember(state):
    directory()
    fd, name = tempfile.mkstemp(prefix='.identity-', dir=ROOT)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(state, output)
        os.replace(name, ROOT / 'identity.json')
    finally:
        Path(name).unlink(missing_ok=True)


def identity():
    path = directory() / 'identity.json'
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        assert info.st_uid == 0 and stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077 and info.st_size < 4096
        return json.load(source)


class LuksBackend:
    """Backend API: capture, lock, unlock, is_unlocked. No caller paths."""
    names = {'os': 'portable_os', 'system': 'portable_system', 'data': 'portable_data'}
    labels = {'os': 'PORTABLE_OS', 'system': 'PORTABLE_SYSTEM', 'data': 'PORTABLE_DATA'}

    def tag(self, device, field):
        return subprocess.check_output(['/usr/sbin/blkid', '-s', field, '-o', 'value', str(device)],
                                       stderr=subprocess.DEVNULL, env=ENV, text=True, timeout=5).strip()

    def capture(self):
        from compartments import ram_ready
        ram_ready()
        from storage_layout import boot_identity
        layout = boot_identity()
        state = {'backend': 'luks', 'layout': layout['layout'], 'devices': {}}
        parents = set()
        kinds = ('os', 'system', 'data') if layout['layout'] == 2 else ('system', 'data')
        for kind in kinds:
            name = self.names[kind]
            mapper = Path('/dev/mapper') / name
            sysfs = None
            if mapper.exists():
                info = mapper.stat()
                assert stat.S_ISBLK(info.st_mode)
                sysfs = Path(f'/sys/dev/block/{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}')
                slaves = list((sysfs / 'slaves').iterdir())
                assert len(slaves) == 1
                device = Path('/dev') / slaves[0].name
            else:
                device = (Path('/dev/disk/by-uuid') / layout['uuids'][kind] if layout['layout'] == 2
                          else Path('/dev/disk/by-label') / self.labels[kind])
            assert self.tag(device, 'TYPE') == 'crypto_LUKS' and self.tag(device, 'LABEL') == self.labels[kind]
            uuid = self.tag(device, 'UUID')
            import uuid as uuid_module
            assert str(uuid_module.UUID(uuid)) == uuid
            if layout['layout'] == 2:
                assert uuid == layout['uuids'][kind]
                raw = device.stat()
                node = Path(f'/sys/dev/block/{os.major(raw.st_rdev)}:{os.minor(raw.st_rdev)}').resolve(strict=True)
                assert (node / 'partition').is_file()
                parents.add(node.parent)
            if sysfs is not None:
                assert (sysfs / 'dm/uuid').read_text().strip().startswith('CRYPT-LUKS2-' + uuid.replace('-', '') + '-')
            raw = device.stat()
            state['devices'][kind] = {'uuid': uuid, 'device_number': raw.st_rdev}
        if layout['layout'] == 2:
            assert len(parents) == 1
            assert len({v['device_number'] for v in state['devices'].values()}) == 3
        return state

    def device(self, state, kind):
        assert state['backend'] == 'luks'
        record = state['devices'][kind]
        device = Path('/dev/disk/by-uuid') / record['uuid']
        info = device.stat()
        assert stat.S_ISBLK(info.st_mode) and info.st_rdev == record['device_number']
        assert self.tag(device, 'UUID') == record['uuid'] and self.tag(device, 'LABEL') == self.labels[kind]
        return device

    def mapped(self, kind):
        return (Path('/dev/mapper') / self.names[kind]).exists()

    def has_active_keys(self, state):
        return any(self.mapped(kind) for kind in state['devices'])

    def private_device_number(self, state):
        if not self.mapped('data'):return None
        self.verify_mapping(state, 'data')
        return (Path('/dev/mapper') / self.names['data']).stat().st_rdev

    def verify_mapping(self, state, kind):
        device = self.device(state, kind)
        mapper = Path('/dev/mapper') / self.names[kind]
        info = mapper.stat()
        sysfs = Path(f'/sys/dev/block/{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}')
        slaves = list((sysfs / 'slaves').iterdir())
        assert len(slaves) == 1 and (Path('/dev') / slaves[0].name).stat().st_rdev == device.stat().st_rdev
        assert (sysfs / 'dm/uuid').read_text().strip().startswith('CRYPT-LUKS2-' + state['devices'][kind]['uuid'].replace('-', '') + '-')

    def lock(self, state):
        from system_state import ready
        if ready():
            # SYSTEM settings have their own boot/screen trust boundary.
            # Private alone must lose its active encryption key here.
            self.close_private(state)
            return
        # SYSTEM is unused after toram boot and holds the automatic DATA key.
        # Close that recovery path first, before draining Private's users.
        if self.mapped('system'):
            self.verify_mapping(state, 'system')
            command(['/usr/sbin/cryptsetup', 'close', self.names['system']])
        self.close_private(state)
        assert not self.mapped('system') and not self.mapped('data')

    def close_private(self, state):
        if self.mapped('data'):
            self.verify_mapping(state, 'data')
            mount = subprocess.run(['/usr/bin/findmnt', '-n', '-o', 'SOURCE', '--mountpoint', str(PRIVATE)],
                                   capture_output=True, env=ENV, text=True, timeout=5)
            if mount.returncode == 0:
                assert mount.stdout.strip() == '/dev/mapper/' + self.names['data']
                command(['/usr/bin/umount', str(PRIVATE)])
            command(['/usr/sbin/cryptsetup', 'close', self.names['data']])
        assert not self.mapped('data')
        PRIVATE.chmod(0o000)

    def unlock(self, state, password):
        # The Private passphrase is the only credential accepted by this API.
        # SYSTEM and its legacy automatic key are never opened/read here.
        assert password is not None
        device = self.device(state, 'data')
        if self.mapped('data'):
            self.verify_mapping(state, 'data')
            command(['/usr/sbin/cryptsetup', 'open', '--test-passphrase', '--key-file', '-', str(device)], password=password, timeout=45)
        else:
            command(['/usr/sbin/cryptsetup', 'open', '--key-file', '-', str(device), self.names['data']], password=password, timeout=45)
        self.verify_mapping(state, 'data')
        mounted_private = subprocess.run(['/usr/bin/mountpoint', '-q', str(PRIVATE)], env=ENV, timeout=5).returncode == 0
        if not mounted_private:
            PRIVATE.mkdir(exist_ok=True)
            command(['/usr/bin/mount', '-o', 'nodev,nosuid,noexec,noatime,x-gvfs-notrash', '/dev/mapper/' + self.names['data'], str(PRIVATE)])
        os.chown(PRIVATE, 1000, 1000);PRIVATE.chmod(0o700)
        assert self.is_unlocked(state)

    def is_unlocked(self, state):
        if not self.mapped('data'):return False
        self.verify_mapping(state, 'data')
        result = subprocess.run(['/usr/bin/findmnt', '-n', '-o', 'SOURCE', '--mountpoint', str(PRIVATE)],
                                capture_output=True, env=ENV, text=True, timeout=5)
        return result.returncode == 0 and result.stdout.strip() == '/dev/mapper/' + self.names['data']

    def authenticate_system(self, state, password):
        # Verify against the SYSTEM header without opening either volume.
        command(['/usr/sbin/cryptsetup', 'open', '--test-passphrase', '--key-file', '-',
                 str(self.device(state, 'system'))], password=password, timeout=45)

    def close_system(self, state):
        if self.mapped('system'):
            self.verify_mapping(state, 'system')
            command(['/usr/sbin/cryptsetup', 'close', self.names['system']])

    def close_os(self, state):
        """After toram, discard the OS mapping; SYSTEM stays independently open."""
        if state.get('layout') != 2 or not self.mapped('os'):
            return
        self.verify_mapping(state, 'os')
        mapper = '/dev/mapper/' + self.names['os']
        check = subprocess.run(['/usr/bin/findmnt', '-n', '--source', mapper],
                               capture_output=True, env=ENV, timeout=5)
        assert check.returncode == 1, 'OS is still mounted; refusing to close the live source.'
        command(['/usr/sbin/cryptsetup', 'close', self.names['os']])

    def evict(self, state):
        for kind in state['devices']:
            name = self.names[kind]
            if self.mapped(kind):
                try:
                    self.verify_mapping(state, kind)
                    command(['/usr/sbin/cryptsetup', 'luksSuspend', name], timeout=2)
                except Exception:pass


def backend():
    # New encryption implementations replace this fixed root-owned adapter.
    # Never load code/configuration from Private or accept caller device paths.
    return LuksBackend()


def power_off():
    command(['/usr/bin/systemctl', 'poweroff', '--force', '--force'], timeout=3)
    raise RuntimeError('Emergency power-off did not terminate the system.')


def private_content_handle(path, device_number):
    try:
        if device_number is not None and path.stat().st_dev==device_number:return True
        return os.readlink(path).startswith(str(DESKTOP_TRASH)+'/')
    except OSError:return False


def kill_private_users(device_number, *, force_workers=False):
    import compartments as c
    for app in c.ROLES:
        record = c.read_record(app)
        if c.worker_alive(record):
            try:
                fd = os.pidfd_open(record['pid'])
                try:
                    if c.worker_alive(record):
                        signal.pidfd_send_signal(fd, signal.SIGKILL if force_workers else signal.SIGTERM)
                finally:os.close(fd)
            except ProcessLookupError:pass
    roles = set(c.ROLES.values())
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal():continue
        try:
            uid = p.stat().st_uid
            affected = uid in roles
            if uid == 1000 and not affected:
                try:
                    affected = Path(os.readlink(p / 'exe')).name in ('Thunar', 'gvfsd-trash', 'xfce4-clipman', 'xfce4-terminal', 'xterm', 'vim.basic.portable-real', 'nano')
                except OSError:pass
                paths = [p / 'cwd', *(p / 'fd').iterdir()]
                affected = affected or any(private_content_handle(path,device_number) for path in paths)
            if affected:
                fd = os.pidfd_open(int(p.name))
                try:signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:os.close(fd)
        except (FileNotFoundError, ProcessLookupError, PermissionError):pass


def lock(*, idle=False):
    # Serialize first: contention is not a storage failure or power-off reason.
    # Test the download inhibition under the same lock as the lock operation.
    with operation():
        if idle and (ROOT / 'download-mode').exists():
            return False
        _lock_locked()
        return True


def _lock_locked():
    adapter = backend()
    state = None
    watchdog = subprocess.Popen(['/usr/bin/python3', '-I', '-c',
        "import sys,time;sys.path.insert(0,'/usr/local/lib/portable');time.sleep(12);from private_storage import power_off;power_off()"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV,
        start_new_session=True)
    try:
        try:state = identity()
        except FileNotFoundError:
            state = adapter.capture();remember(state)
        (ROOT / 'locking').touch(mode=0o600, exist_ok=True)
        (ROOT / 'download-mode').unlink(missing_ok=True)
        from compartments import ram_ready
        ram_ready()
        from volatile_trash import clear as clear_ram_trash, block_private_trash
        block_private_trash()
        # Repeated lock is harmless; actual mappings determine state.
        if not adapter.has_active_keys(state):
            clear_ram_trash()
            kill_private_users(None,force_workers=True)
            return
        number = adapter.private_device_number(state)
        for attempt in range(3):
            kill_private_users(number, force_workers=attempt == 2);time.sleep(.1)
        # Kill copy workers before discarding Private-derived Trash content and
        # its original-path metadata from the desktop's RAM Trash.
        clear_ram_trash()
        # A restarted GVFS reader may have opened an item just before unlink.
        # New copies are blocked; drain these last open handles after clearing.
        kill_private_users(number,force_workers=True)
        # Remove VPN runtime credentials and stop tunnel time traffic.
        command(['/usr/local/sbin/portable-vpn', 'disconnect'], timeout=5)
        command(['/usr/bin/sync', '-f', str(PRIVATE)], timeout=3)
        adapter.lock(state)
        import compartments as c
        for app in c.ROLES:
            c.reset_ram(app)
        # Clear clean page/dentry caches; this does not prove RAM erasure.
        Path('/proc/sys/vm/drop_caches').write_text('3\n')
    except Exception:
        if state is not None:adapter.evict(state)
        power_off()
    finally:
        watchdog.terminate()
        watchdog.wait(timeout=2)


def authenticate_system(password):
    import ctypes, resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    assert ctypes.CDLL('libc.so.6').prctl(4, 0, 0, 0, 0) == 0
    adapter = backend()
    with operation(shared=True):
        try:state = identity()
        except FileNotFoundError:
            state = adapter.capture();remember(state)
        try:adapter.authenticate_system(state, password)
        except Exception:return False
        return True


def unlock(password, *, raise_errors=False):
    # Unlock callers hold a passphrase briefly in RAM. Never permit a core
    # dump or same-UID process inspection of this verifier.
    import ctypes, resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    assert ctypes.CDLL('libc.so.6').prctl(4, 0, 0, 0, 0) == 0
    adapter = backend()
    with operation():
        try:state = identity()
        except FileNotFoundError:
            state = adapter.capture();remember(state)
        opened_before = adapter.is_unlocked(state)
        try:
            adapter.unlock(state, password)
            assert adapter.is_unlocked(state)
            from volatile_trash import allow_private_trash
            allow_private_trash()
        except Exception:
            if opened_before:
                # Failed password verification must not alter an already-open
                # volume; no new key was installed in this branch.
                if raise_errors:
                    raise
                return False
            # Roll back only DATA opened by this attempt. First-boot admin
            # provisioning may legitimately still need SYSTEM mounted/open.
            try:adapter.close_private(state)
            except Exception:
                adapter.evict(state);power_off()
            if raise_errors:
                raise
            return False
        (ROOT / 'locking').unlink(missing_ok=True)
        return adapter.is_unlocked(state)


def boot_unlock():
    adapter = backend()
    with operation():
        state = adapter.capture();remember(state)
        from volatile_trash import block_private_trash
        block_private_trash()
        (ROOT / 'locking').touch(mode=0o600, exist_ok=True)
        # SYSTEM settings are available before the desktop without opening DATA.
        from system_state import prepare
        prepare(state)
        # Layout 2's OS contains no credentials or writable settings. It is
        # no longer needed after live-boot has copied its payload to RAM.
        if state.get('layout') == 2:
            adapter.close_os(state)
        if not adapter.mapped('data'):
            PRIVATE.mkdir(exist_ok=True);PRIVATE.chmod(0o000)
