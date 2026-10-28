#!/usr/bin/python3 -B
"""Compatibility entry point for the current real public signature tests.

The old wrapper unpacked the archive itself. The compartment worker now owns
that operation; test its signed OS-bundle selection and fail-closed behavior.
"""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('check-bundled-tor.py')),run_name='__main__')
