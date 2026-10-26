"""Strict UTC input for offline clock recovery; never writes the hardware clock."""
from datetime import datetime, timezone
import re

def parse(value):
    if not isinstance(value, str) or not re.fullmatch(r'20\d\d-\d\d-\d\d \d\d:\d\d:\d\d', value):
        raise ValueError('Use UTC time in YYYY-MM-DD HH:MM:SS format.')
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()
