#!/usr/bin/python3 -I
"""Public boot-event categories/timing only; never export raw console messages."""
import json
import re
import subprocess

rows = subprocess.check_output(['dmesg', '--color=never'], text=True)
events = []
for row in rows.splitlines():
    parsed = re.match(r'^\[\s*(\d+\.\d+)\]\s+(.*)', row)
    if not parsed:continue
    message = parsed.group(2).lower()
    for match, label in [('crng init done', 'kernel_entropy_ready'),
                         ('ext4-fs (dm-0): mounted', 'SYSTEM_filesystem_mounted')]:
        if match in message:
            events.append({'event': label, 'kernel_event_seconds': float(parsed.group(1))})
print(json.dumps({'boot_events': events}))
