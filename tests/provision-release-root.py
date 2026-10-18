#!/usr/bin/env python3
"""Update the base release and public SSH layer using strict clone checks."""
import importlib.util
from pathlib import Path
import sys

try:
    if len(sys.argv)!=4:raise RuntimeError('Expected clone, release and public SSH module.')
    _,raw,release,module=sys.argv
    spec=importlib.util.spec_from_file_location('updater',Path(__file__).with_name('update-encrypted-clone.py'))
    updater=importlib.util.module_from_spec(spec);spec.loader.exec_module(updater)
    sys.argv=[sys.argv[0],raw,release]
    updater.main(replacement_ssh_module=module)
except Exception as error:
    print(str(error),file=sys.stderr);sys.exit(1)
