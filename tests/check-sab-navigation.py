#!/usr/bin/python3
"""Exercise the actual viewer navigation/permission handlers without WebKit."""
import ast
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

project = Path(__file__).resolve().parents[1]
tree = ast.parse((project / 'config/includes.chroot/usr/local/bin/portable-sab-view').read_text())
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('decide_policy','deny_permission')]
scope = {'urlsplit':urlsplit, 'WebKit2':SimpleNamespace(PolicyDecisionType=SimpleNamespace(NEW_WINDOW_ACTION=1,NAVIGATION_ACTION=2))}
exec(compile(ast.Module(body=functions,type_ignores=[]),'<actual-viewer-handlers>','exec'),scope)
for uri, allowed in [('about:blank',True),('http://127.0.0.1:8080/',True),
    ('http://127.0.0.1:8080/settings',True),('https://example.org/',False),
    ('http://127.0.0.1:80/',False),('http://localhost:8080/',False),
    ('http://user@127.0.0.1:8080/',False),('file:///etc/passwd',False),
    ('http://127.0.0.1:bad/',False),('https://127.0.0.1:8080/',False)]:
    ignored=[]
    decision=SimpleNamespace(ignore=lambda:ignored.append(True),
        get_navigation_action=lambda:SimpleNamespace(get_request=lambda:SimpleNamespace(get_uri=lambda:uri)))
    result=scope['decide_policy'](None,decision,2)
    assert bool(ignored)==(not allowed) and result==(not allowed)
    print('PASS: SAB navigation '+('allows local view' if allowed else 'rejects other target'))
ignored=[]
scope['decide_policy'](None,SimpleNamespace(ignore=lambda:ignored.append(True)),1)
assert ignored
denied=[]
assert scope['deny_permission'](None,SimpleNamespace(deny=lambda:denied.append(True))) is True and denied
print('PASS: SAB rejects popups and permission requests')
