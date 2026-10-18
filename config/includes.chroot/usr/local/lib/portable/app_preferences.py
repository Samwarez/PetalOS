"""Explicit preference snapshots: bounded allowlists, never whole app profiles."""
import configparser
import ipaddress
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import xml.etree.ElementTree as ET

LIMIT = 1024 * 1024
# Bounds describe preferences, never filenames, identities, credentials or counters.
BOOL = ('bool', 0, 1)
SPECS = {
 'transmission': ('json', 'settings.json', {
  'speed-limit-down': ('int',0,10000000), 'speed-limit-up': ('int',0,10000000),
  'speed-limit-down-enabled': BOOL, 'speed-limit-up-enabled': BOOL,
  'alt-speed-down': ('int',0,10000000), 'alt-speed-up': ('int',0,10000000),
  'peer-limit-global': ('int',1,10000), 'peer-limit-per-torrent': ('int',1,1000)}),
 'amule': ('ini', 'amule.conf', {
  'eMule/MaxDownload': ('int',0,65535), 'eMule/MaxUpload': ('int',0,65535),
  'eMule/MaxConnections': ('int',1,10000), 'eMule/SlotAllocation': ('int',1,65535),
  'eMule/MaxSourcesPerFile': ('int',1,10000),
  # Reviewed against aMule 2.3.3 Preferences.cpp. Never persist arbitrary
  # strings, paths, commands, identities, counters or last-used state here.
  'eMule/Port': ('int',1,65535), 'eMule/UDPPort': ('int',1,65535),
  'eMule/UDPEnable': BOOL, 'eMule/Autoconnect': BOOL,
  'eMule/MaxConnectionsPerFiveSeconds': ('int',1,1000),
  'eMule/QueueSizePref': ('int',1,255),
  'eMule/RemoveDeadServer': BOOL, 'eMule/DeadServerRetry': ('int',1,100),
  'eMule/ServerKeepAliveTimeout': ('int',0,1440), 'eMule/Reconnect': BOOL,
  'eMule/Scoresystem': BOOL, 'eMule/SafeServerConnect': BOOL,
  'eMule/AutoConnectStaticOnly': BOOL, 'eMule/SmartIdCheck': BOOL,
  'eMule/ConnectToKad': BOOL, 'eMule/ConnectToED2K': BOOL,
  'eMule/ICH': BOOL, 'eMule/CheckDiskspace': BOOL,
  'eMule/MinFreeDiskSpace': ('int',1,1048576), 'eMule/AddNewFilesPaused': BOOL,
  'eMule/PreviewPrio': BOOL, 'eMule/ManualHighPrio': BOOL,
  'eMule/StartNextFile': BOOL, 'eMule/StartNextFileSameCat': BOOL,
  'eMule/StartNextFileAlpha': BOOL, 'eMule/FileBufferSizePref': ('int',1,255),
  'eMule/DAPPref': BOOL, 'eMule/UAPPref': BOOL,
  'eMule/AllocateFullFile': BOOL, 'eMule/CreateSparseFiles': BOOL,
  'eMule/EnableTrayIcon': BOOL, 'eMule/MinToTray': BOOL,
  'eMule/Notifications': BOOL, 'eMule/ConfirmExit': BOOL,
  'eMule/StartupMinimized': BOOL, 'GUI/HideOnClose': BOOL,
  'eMule/3DDepth': ('int',0,10), 'eMule/ToolTipDelay': ('int',0,255),
  'eMule/ShowOverhead': BOOL, 'eMule/ShowInfoOnCatTabs': BOOL,
  'eMule/VerticalToolbar': BOOL, 'eMule/GeoIPEnabled': BOOL,
  'eMule/ShowVersionOnTitle': BOOL, 'eMule/ShowRatesOnTitle': ('int',0,3),
  'eMule/StatGraphsInterval': ('int',0,60), 'eMule/statsInterval': ('int',0,3600),
  'eMule/DownloadCapacity': ('int',0,10000000),
  'eMule/UploadCapacity': ('int',0,10000000),
  'eMule/StatsAverageMinutes': ('int',1,255),
  'eMule/VariousStatisticsMaxValue': ('int',1,255),
  'Statistics/MaxClientVersions': ('int',0,1000),
  'eMule/AutoSortDownloads': BOOL, 'eMule/DropSlowSources': BOOL,
  'eMule/FilterMessages': BOOL, 'eMule/FilterAllMessages': BOOL,
  'eMule/MessagesFromFriendsOnly': BOOL, 'eMule/MessageFromValidSourcesOnly': BOOL,
  'eMule/FilterWordMessages': BOOL, 'eMule/AdvancedSpamFilter': BOOL,
  'eMule/MessageUseCaptchas': BOOL, 'eMule/FilterComments': BOOL,
  'eMule/FilterLanIPs': BOOL, 'eMule/ParanoidFiltering': BOOL,
  'eMule/FilterLevel': ('int',0,255), 'eMule/IPFilterSystem': BOOL,
  'ExternalConnect/IpFilterClients': BOOL, 'ExternalConnect/IpFilterServers': BOOL,
  'ExternalConnect/UseSecIdent': BOOL,
  'Obfuscation/IsClientCryptLayerSupported': BOOL,
  'Obfuscation/IsCryptLayerRequested': BOOL,
  'Obfuscation/IsClientCryptLayerRequired': BOOL}),
 'pan': ('xml', 'preferences.xml', {'cache-size-megs': ('int',1,1024)}),
 'offline-geany': ('ini', '.config/geany/geany.conf', {
  'geany/pref_editor_tab_width': ('int',1,16), 'geany/indent_type': ('int',0,2),
  'geany/line_wrapping': BOOL, 'geany/show_line_number_margin': BOOL}),
 'offline-keepassxc': ('ini', '.config/keepassxc/keepassxc.ini', {
  'GUI/MinimizeOnClose': BOOL, 'GUI/MinimizeToTray': BOOL}),
 'offline-quodlibet': ('ini', '.config/quodlibet/config', {'player/volume': ('float',0,1)}),
}


def scalar(value, spec):
    kind, low, high = spec
    if kind == 'bool':
        if type(value) is bool:return value
        if value in ('true','True','1'):return True
        if value in ('false','False','0'):return False
        raise ValueError('Invalid boolean preference.')
    if type(value) is bool:raise ValueError('Invalid numeric preference.')
    if kind == 'float':
        if not isinstance(value,(str,int,float)):raise ValueError('Invalid volume preference.')
        value=float(value)
        if not low<=value<=high:raise ValueError('Preference outside permitted range.')
        return value
    if not isinstance(value,(str,int)) or (isinstance(value,str) and not value.isdecimal()):
        raise ValueError('Invalid numeric preference.')
    value=int(value)
    if not low<=value<=high:raise ValueError('Preference outside permitted range.')
    return value


def read_bounded(root, relative, owners):
    """Open every path component without following app-controlled symlinks."""
    parts=Path(relative).parts
    assert parts and not Path(relative).is_absolute() and '..' not in parts
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        leaf=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            info=os.fstat(leaf)
            assert stat.S_ISREG(info.st_mode) and info.st_uid in owners and info.st_size<=LIMIT
            chunks=[];total=0
            while chunk:=os.read(leaf,min(65536,LIMIT+1-total)):
                total+=len(chunk);assert total<=LIMIT;chunks.append(chunk)
            return b''.join(chunks)
        finally:os.close(leaf)
    finally:os.close(fd)


def filtered(app, data):
    kind,_,schema=SPECS[app]
    if kind=='json':values=json.loads(data)
    elif kind=='ini':
        c=configparser.ConfigParser(interpolation=None,strict=False);c.optionxform=str
        c.read_string(data.decode('utf-8'))
        values={key:c.get(*key.split('/',1)) for key in schema if c.has_option(*key.split('/',1))}
    else:
        assert b'\x00' not in data and b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper()
        tree=ET.fromstring(data);assert tree.tag=='preferences'
        values={e.get('name'):e.get('value') for e in tree if e.tag=='int'}
    assert isinstance(values,dict)
    result={}
    for key,spec in schema.items():
        if key in values:
            try:result[key]=scalar(values[key],spec)
            except ValueError:pass
    return result


def endpoints(data):
    """Discard every server.met tag; retain only numeric server addresses/ports."""
    assert len(data)<=LIMIT and len(data)>=5 and data[0] in (0x0e,0xe0)
    count=struct.unpack_from('<I',data,1)[0];assert count<=4096
    pos=5;result=set()
    def take(n):
        nonlocal pos
        assert 0<=n<=LIMIT and pos+n<=len(data)
        value=data[pos:pos+n];pos+=n;return value
    def number(n):return int.from_bytes(take(n),'little')
    for _ in range(count):
        address=number(4);port=number(2);tags=number(4);assert tags<=256
        ip=ipaddress.IPv4Address(address)
        if ip.is_global and 1<=port<=65535:result.add((str(ip),port))
        for _ in range(tags):
            tag=number(1)
            if tag&0x80:take(1);tag&=0x7f
            else:take(number(2))
            if tag==2:take(number(2))
            elif tag in (1,3,4,5,8,9,11):take({1:16,3:4,4:4,5:1,8:2,9:1,11:8}[tag])
            elif tag==6:take((number(2)+7)//8)
            elif tag==7:take(number(4))
            elif tag==10:take(number(1))
            elif 0x11<=tag<=0x20:take(tag-0x10)
            else:raise ValueError('Unsupported server-list tag.')
    assert pos==len(data)
    return [[a,p] for a,p in sorted(result)]


def validate(app, record):
    assert set(record)=={'version','preferences','servers'} and record['version']==1
    schema=SPECS[app][2];values=record['preferences'];assert isinstance(values,dict)
    assert set(values)<=set(schema)
    result={k:scalar(v,schema[k]) for k,v in values.items()}
    servers=record['servers'];assert isinstance(servers,list) and len(servers)<=4096
    clean=[]
    for entry in servers:
        assert app=='amule' and isinstance(entry,list) and len(entry)==2
        ip,port=entry;assert isinstance(ip,str) and ipaddress.IPv4Address(ip).is_global
        assert type(port) is int and 1<=port<=65535
        clean.append([ip,port])
    return {'version':1,'preferences':result,'servers':sorted(clean)}


def atomic(path, data, mode=0o600):
    path=Path(path)
    assert not path.is_symlink()
    fd,name=tempfile.mkstemp(prefix='.preferences-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as output:
            os.fchmod(output.fileno(),mode);output.write(data);output.flush();os.fsync(output.fileno())
        os.replace(name,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:Path(name).unlink(missing_ok=True)


def store():
    from system_state import STATE,require
    require();path=STATE/'AppPreferences'
    assert not path.is_symlink();path.mkdir(mode=0o700,exist_ok=True)
    info=path.stat();assert info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700
    return path


def save_all():
    import compartments as c
    assert os.geteuid()==0
    # Avoid partially saved app files. This operation never stops an app for you.
    assert not any(c.worker_alive(c.read_record(app)) for app in SPECS)
    target=store();records={}
    for app in SPECS:
        if app in ('transmission','pan','amule'):
            private=c.read_record(app).get('storage')=='private'
            if private:assert c.private_available()
            root=c.PRIVATE/'AppState'/app if private else c.PAYLOAD/app/'state'
        else:root=c.PAYLOAD/app/'home'
        if not root.exists():continue
        try:data=read_bounded(root,SPECS[app][1],{1000,c.ROLES[app]})
        except FileNotFoundError:continue
        record={'version':1,'preferences':filtered(app,data),'servers':[]}
        if app=='amule':
            try:record['servers']=endpoints(read_bounded(root,'server.met',{1000,c.ROLES[app]}))
            except FileNotFoundError:pass
        records[app]=validate(app,record)
    for app,record in records.items():
        destination=target/(app+'.json');data=json.dumps(record,sort_keys=True).encode()
        try:old=read_bounded(target,destination.name,{0})
        except FileNotFoundError:old=None
        if old!=data:atomic(destination,data)
    return len(records)


def snapshot(app, destination):
    assert os.geteuid()==0
    if app not in SPECS:return False
    from system_state import STATE,require
    require()
    if not (STATE/'AppPreferences').exists():return False
    try:data=read_bounded(store(),app+'.json',{0})
    except FileNotFoundError:return False
    record=validate(app,json.loads(data));atomic(destination,json.dumps(record).encode(),0o444)
    return True


def apply(app):
    """Runs as the app's real UID, inside its mount namespace; never as root."""
    import compartments as c
    assert os.getuid()==c.ROLES[app] and os.geteuid()!=0
    source=Path('/run/petalos-preferences.json')
    if not source.exists():return
    record=validate(app,json.loads(source.read_bytes()))
    if app in ('transmission','pan','amule'):
        prefix=os.environ['PORTABLE_STATE_ROOT'];assert prefix in ('/mnt/ram','/mnt/private')
        root=Path(prefix)/'AppState'/app
    else:root=Path.home()
    kind,relative,_=SPECS[app];path=root/relative;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    assert not path.is_symlink()
    try:data=path.read_bytes();assert len(data)<=LIMIT
    except FileNotFoundError:data=b''
    if kind=='json':
        values=json.loads(data) if data else json.loads(Path('/usr/local/share/portable/transmission-defaults.json').read_bytes())
        values.update(record['preferences'])
        output=json.dumps(values).encode()
    elif kind=='ini':
        cfg=configparser.ConfigParser(interpolation=None,strict=False);cfg.optionxform=str
        if data:cfg.read_string(data.decode())
        for key,value in record['preferences'].items():
            section,name=key.split('/',1)
            if not cfg.has_section(section):cfg.add_section(section)
            # wxConfig reads aMule booleans as integers; words silently fall
            # back to the application's default instead of restoring False.
            encoded=str(int(value)) if app=='amule' and type(value) is bool else str(value).lower()
            cfg.set(section,name,encoded)
        import io
        stream=io.StringIO();cfg.write(stream,space_around_delimiters=False);output=stream.getvalue().encode()
    else:
        tree=ET.fromstring(data) if data else ET.Element('preferences')
        if not data:
            ET.SubElement(tree,'string',name='default-save-attachments-path',
                value=os.environ['PORTABLE_STATE_ROOT']+'/Downloads/pan')
        for key,value in record['preferences'].items():
            entry=next((e for e in tree if e.get('name')==key),None)
            if entry is None:entry=ET.SubElement(tree,'int',name=key)
            entry.set('value',str(value))
        output=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
    atomic(path,output)
    if app=='amule' and record['servers'] and not (root/'server.met').exists():
        # Fresh minimal server.met: no names, timestamps, pings or usage tags.
        data=b'\xe0'+struct.pack('<I',len(record['servers']))
        for ip,port in record['servers']:data+=struct.pack('<IHI',int(ipaddress.IPv4Address(ip)),port,0)
        atomic(root/'server.met',data)
