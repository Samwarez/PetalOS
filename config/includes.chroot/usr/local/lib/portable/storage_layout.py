"""Public storage identities for legacy media and the five-partition layout."""
from pathlib import Path
import uuid

LABELS = {'os': 'PORTABLE_OS', 'system': 'PORTABLE_SYSTEM', 'data': 'PORTABLE_DATA'}
MAPPERS = {'os': 'portable_os', 'system': 'portable_system', 'data': 'portable_data'}


def boot_identity(command_line=None):
    text = Path('/proc/cmdline').read_text() if command_line is None else command_line
    fields = {}
    for item in text.split():
        if item.startswith(('petalos.layout=', 'petalos.os=', 'petalos.system=', 'petalos.private=')):
            key, value = item.split('=', 1)
            if key in fields:
                raise RuntimeError('Duplicate encrypted-storage boot identity.')
            fields[key] = value
    if 'petalos.layout' not in fields:
        if fields:
            raise RuntimeError('Encrypted-storage identities require a layout version.')
        return {'layout': 1, 'uuids': {}}
    if fields.get('petalos.layout') != '2' or set(fields) != {
            'petalos.layout', 'petalos.os', 'petalos.system', 'petalos.private'}:
        raise RuntimeError('Incomplete split-storage boot identity.')
    values = {kind: fields[key] for kind, key in (
        ('os', 'petalos.os'), ('system', 'petalos.system'), ('data', 'petalos.private'))}
    if any(str(uuid.UUID(value)) != value for value in values.values()) or len(set(values.values())) != 3:
        raise RuntimeError('Split-storage volumes must have distinct canonical identities.')
    if 'live-media=/dev/mapper/portable_os' not in text.split():
        raise RuntimeError('Split-storage boot must use the encrypted OS volume.')
    return {'layout': 2, 'uuids': values}
