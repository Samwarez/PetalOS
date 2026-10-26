from pathlib import Path
import errno, json, os
assert os.geteuid()==0
folder=Path('/home/Petal/Documents/keepassxc')
assert os.path.ismount(folder)
with (folder/'public-gui-fixture.fill').open('xb',buffering=0) as f:
    os.fchown(f.fileno(),1000,1000)
    try:
        while True:f.write(bytes(65536))
    except OSError as error:
        assert error.errno==errno.ENOSPC
print(json.dumps({'synthetic_destination_full':True}))
