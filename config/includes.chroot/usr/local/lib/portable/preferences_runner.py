#!/usr/bin/python3 -I
"""Restore approved preferences as the already isolated application's UID."""
import os
import sys
sys.path.insert(0, '/usr/local/lib/portable')
from compartments import inside
from app_preferences import apply
app = sys.argv[1]
assert sys.argv[2] == '--' and inside(app)
apply(app)
os.execvp(sys.argv[3], sys.argv[3:])
