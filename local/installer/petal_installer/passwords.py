"""Role-based creation policy and local, advisory password strength estimates."""
import ctypes
from functools import lru_cache
import math

MINIMUM_CHARACTERS = {'system': 15, 'administrator': 15, 'private': 24}
ROLE_NAMES = {'system': 'SYSTEM', 'administrator': 'Administrator', 'private': 'Private'}


@lru_cache(maxsize=1)
def _matcher():
    # Debian's public zxcvbn-c library includes its pattern/dictionary data.
    # No subprocess, network service, cache of passwords or persisted score.
    library = ctypes.CDLL('libzxcvbn.so.0')
    match = library.ZxcvbnMatch
    match.argtypes = (ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p), ctypes.c_void_p)
    match.restype = ctypes.c_double
    return match


def strength(value, role):
    """Return presentation only; never return or cache the supplied password.

    zxcvbn-c counts bytes. Decline non-ASCII estimates rather than inflating
    strength from UTF-8 bytes. Limit matching to a conservative 128-char prefix
    to keep typing responsive even at the backend's 512-byte input limit.
    """
    minimum = MINIMUM_CHARACTERS[role]
    length = len(value)
    requirement = (f'{length}/{minimum} characters' if length < minimum else
                   f'{length} characters · minimum met')
    if not value:
        return {'score': 0, 'text': f'At least {minimum} characters'}
    try:
        encoded = value[:128].encode('ascii')
        if any(c < 32 or c > 126 for c in encoded):raise ValueError()
        context = (ctypes.c_char_p * 5)(b'bloom', b'petalos', b'private', b'administrator', None)
        estimate = _matcher()(encoded, context, None)
        if not math.isfinite(estimate) or estimate < 0:raise ValueError()
    except (OSError, AttributeError, ValueError, UnicodeError):
        return {'score': 0, 'text': requirement + ' · strength estimate unavailable'}
    # Conservative display bands, not a claim about actual entropy or time to
    # crack. Minimum-length compliance and estimated strength stay separate.
    score = sum(estimate >= threshold for threshold in (20, 36, 60, 80))
    title = ('Very weak', 'Weak', 'Fair', 'Strong', 'Very strong')[score]
    return {'score': score, 'text': title + ' estimate · ' + requirement}
