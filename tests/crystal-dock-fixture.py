#!/usr/bin/python3
"""Guarded headless Labwc fixture; fake launch endpoints, never a live session."""
from pathlib import Path
import json,os,shutil,signal,subprocess,time

assert os.getuid()==1000
mapping=Path('/proc/self/uid_map').read_text().split();assert len(mapping)==3 and mapping[0]=='1000' and mapping[2]=='1'
assert Path('/test/crystal-fixture-only').read_text()=='isolated public Crystal Dock fixture\n'
home=Path(os.environ['HOME']);home.mkdir(mode=0o700,exist_ok=True)
apps=Path('/usr/share/applications');apps.mkdir(parents=True,exist_ok=True)
shutil.copytree('/inputs/usr/share/icons','/usr/share/icons',dirs_exist_ok=True)
bin=Path('/usr/local/bin');bin.mkdir(parents=True,exist_ok=True)
for name in ('portable-desktop','portable-lock','portable-download-mode','portable-vpn-profiles','portable-tor-install'):
    p=bin/name;p.write_text('#!/bin/sh\nprintf "%s\\n" "'+name+' $*" >>/test/launches\n');p.chmod(0o755)
Path('/usr/bin/exo-open').write_text('#!/bin/sh\nprintf "%s\\n" "exo-open $*" >>/test/launches\n');Path('/usr/bin/exo-open').chmod(0o755)
for name in ('xfce4-terminal-emulator','xfce4-file-manager'):
    command='exo-open --launch '+('TerminalEmulator' if 'terminal' in name else 'FileManager')
    (apps/(name+'.desktop')).write_text('[Desktop Entry]\nType=Application\nName='+name+'\nIcon='+('utilities-terminal' if 'terminal' in name else 'system-file-manager')+'\nExec='+command+'\nCategories=System;\nOnlyShowIn=XFCE;\n')
for source in Path('/inputs/usr/share/applications').glob('*.desktop'):
    if source.name.startswith('portable-'):shutil.copyfile(source,apps/source.name)
shutil.copyfile('/inputs/usr/local/bin/portable-helpers',bin/'portable-helpers');(bin/'portable-helpers').chmod(0o755)
shutil.copyfile('/inputs/usr/local/libexec/portable-crystal-dock',bin/'start-dock');(bin/'start-dock').chmod(0o755)
# Capture only this public fixture's diagnostics instead of normal-session silence.
(bin/'start-dock').write_text((bin/'start-dock').read_text().replace('>/dev/null 2>&1',''))
shutil.copytree('/inputs/etc/xdg/crystal-dock','/etc/xdg/crystal-dock',dirs_exist_ok=True)
preset=Path('/etc/xdg/crystal-dock/XFCE/panel_1.conf')
preset.write_text(preset.read_text().replace('showVersionChecker=false','showVersionChecker=true').replace('showWifiManager=false','showWifiManager=true'))
background=subprocess.Popen(['swaybg','-i','/inputs/usr/share/backgrounds/petalos-defaults/04-petal-drift.png','-m','fill'],stdout=open('/test/background.log','wb'),stderr=subprocess.STDOUT)
checks={}
traces=[]
log=open('/test/dock.log','wb')
def launch():return subprocess.Popen(['strace','-f','-e','trace=network','-o','/test/network.trace','/usr/local/bin/start-dock'],stdout=log,stderr=log)
dock=launch()
try:
    time.sleep(4);assert dock.poll() is None
    checks['native_launch_alive']=True
    cfg=home/'.config/crystal-dock/XFCE/panel_1.conf';assert cfg.is_file()
    checks['preset_without_welcome']=all(v in cfg.read_text() for v in ('portable-tor','portable-helpers','lock-screen'))
    subprocess.run(['grim','/test/dock.png'],check=True,timeout=5)
    second=subprocess.run(['/output/crystal-dock'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
    checks['single_instance_refused']=second.returncode!=0
    # Move in two steps and let the hover animation settle, as a real pointer
    # does, rather than teleporting and pressing within the same frame.
    x,y=100,100
    def click_at(nx,ny):
        global x,y
        subprocess.run(['wlrctl','pointer','move',str(nx-x),str(ny-y)],check=True,timeout=3)
        x,y=nx,ny
        subprocess.run(['wlrctl','pointer','move','1','0'],check=True,timeout=3);x+=1
        time.sleep(.7)
        subprocess.run(['wlrctl','pointer','click','left'],check=True,timeout=3)
        time.sleep(.5)
    click_at(497,678)
    click_at(560,678)
    click_at(623,678)
    click_at(720,678)
    for attempt in range(15):
        listing=subprocess.run(['wlrctl','toplevel','list'],capture_output=True,text=True,timeout=3)
        if 'PetalOS Helpers' in listing.stdout:break
        time.sleep(.2)
    checks['helper_window_tracked']='PetalOS Helpers' in listing.stdout
    subprocess.run(['grim','/test/helpers.png'],check=True,timeout=5)
    click_at(784,678);time.sleep(.5)
    requests=Path('/test/launches').read_text().splitlines() if Path('/test/launches').exists() else []
    checks['terminal_launcher']='exo-open --launch TerminalEmulator' in requests
    checks['file_manager_launcher']='exo-open --launch FileManager' in requests
    checks['Tor_guarded_launcher']='portable-desktop tor' in requests
    checks['guarded_lock_action']=any(line.startswith('portable-lock ') for line in requests)
    (Path('/test/ready')).touch()
    # A separate controller may exercise clicks on this isolated dock.
    deadline=time.monotonic()+10
    while time.monotonic()<deadline and not Path('/test/finish').exists():
        assert dock.poll() is None
        request=Path('/test/control.json')
        if request.exists():
            commands=json.loads(request.read_text());request.unlink()
            replies=[]
            for args in commands:
                assert isinstance(args,list) and args[0] in ('pointer','keyboard','toplevel') and all(isinstance(a,str) for a in args)
                result=subprocess.run(['wlrctl',*args],capture_output=True,text=True,timeout=3)
                replies.append({'exit':result.returncode,'stdout':result.stdout[-2000:],'stderr':result.stderr[-2000:]})
            Path('/test/control-result.json').write_text(json.dumps(replies))
            subprocess.run(['grim','/test/after-click.png'],check=True,timeout=5)
        time.sleep(.2)
    checks['launcher_requests']=(Path('/test/launches').read_text().splitlines() if Path('/test/launches').exists() else [])
    traces.append(Path('/test/network.trace').read_text())
    # Close the public helper window, then kill only this dock inside the
    # namespace to exercise stale shared-memory recovery without a reboot.
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal():continue
        try:
            args=(process/'cmdline').read_bytes().split(b'\0')
            if b'/usr/local/bin/portable-helpers' in args:os.kill(int(process.name),signal.SIGTERM)
            if os.readlink(process/'exe')=='/usr/bin/crystal-dock':os.kill(int(process.name),signal.SIGKILL)
        except (OSError,ProcessLookupError):pass
    dock.wait(timeout=5)
    appearance=home/'.config/crystal-dock/XFCE/appearance.conf'
    appearance.write_text(appearance.read_text().replace('tooltipFontSize=12','tooltipFontSize=13'))
    dock=launch();time.sleep(3)
    checks['restart_after_crash']=dock.poll() is None
    checks['custom_preferences_survive_restart']='tooltipFontSize=13' in appearance.read_text()
    subprocess.run(['grim','/test/restarted.png'],check=True,timeout=5)
    traces.append(Path('/test/network.trace').read_text())
    checks['no_internet_socket_calls']=all('socket(AF_INET' not in trace for trace in traces)
finally:
    # Terminate only the fixture's traced process tree inside its PID namespace.
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal():continue
        try:
            if os.readlink(process/'exe') in ('/output/crystal-dock','/usr/bin/crystal-dock'):
                os.kill(int(process.name),signal.SIGTERM)
        except (OSError,ProcessLookupError):pass
    try:dock.wait(timeout=5)
    except subprocess.TimeoutExpired:dock.kill();dock.wait()
    log.close()
Path('/test/result.json').write_text(json.dumps(checks,indent=2)+'\n')
assert all(checks[k] for k in ('native_launch_alive','preset_without_welcome','single_instance_refused',
                             'no_internet_socket_calls','helper_window_tracked','terminal_launcher',
                             'file_manager_launcher','Tor_guarded_launcher','guarded_lock_action',
                             'restart_after_crash','custom_preferences_survive_restart'))
