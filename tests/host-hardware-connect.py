#!/usr/bin/python3 -I
"""Fixed child of localhost relay; no keys, caller destinations or shell."""
import os

assert os.geteuid() == 0
fd = os.open('/run/netns/petalos-host-management', os.O_RDONLY)
try: os.setns(fd, 0)
finally: os.close(fd)
os.execv('/usr/bin/socat', ['socat', 'STDIO', 'TCP4:198.18.0.2:22,connect-timeout=5'])
