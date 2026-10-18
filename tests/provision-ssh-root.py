#!/usr/bin/env python3
"""Use the existing strict clone identity checks for a QEMU-only SSH module."""
import importlib.util
from pathlib import Path
import sys

if __name__ == '__main__':
    try:
        if len(sys.argv) != 5:
            raise RuntimeError('Expected clone, release, module and public-key destination.')
        _, raw, release, module, public_key = sys.argv
        spec = importlib.util.spec_from_file_location('updater', Path(__file__).with_name('update-encrypted-clone.py'))
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)
        sys.argv = [sys.argv[0], raw, release]
        updater.main(ssh_module=module, host_public_key=public_key)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
