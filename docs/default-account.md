# Default OS account

The OS creates `Petal`, UID 1000, independently of Private. Desktop autologin
is retained, but Petal password authentication is disabled; there is no fourth
user-login password. Key-authenticated QEMU maintenance SSH remains available.

Three independent human secrets are used:

- SYSTEM passphrase: boots the encrypted OS and unlocks the desktop screen.
- Administrator password: authorizes sudo and polkit administration.
- Private passphrase: opens only Private through its separate unlock action.

The administrator password is provisioned graphically. Only its salted hash is
stored at `/.petalos-auth/root-admin.hash` inside encrypted SYSTEM, outside
`filesystem.squashfs`. It is restored into RAM during boot, before preparing the selective SYSTEM settings store.
A fresh installation needs provisioning once. Secrets are not build inputs.

The staged configuration does not automatically unlock Private from the SYSTEM-volume key.
Screen unlock verifies SYSTEM without reopening Private; the separate system
settings store remains available. Private stays locked until its own passphrase
is supplied through the existing unlock action. Its existing
desktop unlock shortcut requests the Private passphrase directly, without an
administrator-password prompt. The old automatic DATA key slot in existing
installations has not been removed: retiring it is a separate reviewed storage
change. No physical-card key slots were changed.

The retired public Petal login belonged to earlier releases, including
`20261012-205248-827255`; it is superseded by the staged configuration above.
QEMU verified disabled Petal password authentication with a new key-authenticated
SSH connection, live encrypted-volume locking and Private-passphrase storage unlocking.
The corrected SYSTEM-only screen verifier passed synthetic and live checks:
Sam unlocked the desktop while Private stayed closed. The read-only full SYSTEM
view and selected persistent settings are described in [system-state storage](system-state.md).
A rebuilt cold boot and autologin with these changes remain unverified.

Fixed storage operations, the validated application broker and readiness checks
have scoped passwordless exceptions. They accept fixed actions, not arbitrary
commands or device paths. General administration requires the administrator
password. See [storage lock checks](private-lock-20261013.md).
