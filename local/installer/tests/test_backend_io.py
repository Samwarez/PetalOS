from pathlib import Path
import subprocess
import sys
import unittest


class BackendPipeTests(unittest.TestCase):
    def isolated(self, body):
        source = Path(__file__).resolve().parents[1] / 'backend.py'
        script = '''import importlib.util,os,threading
from pathlib import Path
source=Path(''' + repr(str(source)) + ''')
spec=importlib.util.spec_from_file_location('worker',source)
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
''' + body
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', script], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_packet_does_not_prefetch_immediately_queued_cancellation(self):
        self.isolated('''read,write=os.pipe()
os.write(write,b'{"request":{},"credentials":{}}\\n{"cancel":true}\\n')
assert worker.read_packet(read)==b'{"request":{},"credentials":{}}\\n'
finished=threading.Event();cancelled=threading.Event()
thread=threading.Thread(target=worker.monitor_client,args=(read,finished,cancelled.set))
thread.start();thread.join(2)
assert not thread.is_alive() and cancelled.is_set()
os.close(read);os.close(write)
''')

    def test_success_exits_cleanly_with_the_client_pipe_still_open(self):
        self.isolated('''read,write=os.pipe();finished=threading.Event();cancelled=threading.Event()
thread=threading.Thread(target=worker.monitor_client,args=(read,finished,cancelled.set),daemon=True)
thread.start();finished.set();thread.join(2)
assert not thread.is_alive() and not cancelled.is_set()
os.close(read);os.close(write)
''')

    def test_client_eof_cancels_an_active_job(self):
        self.isolated('''read,write=os.pipe();finished=threading.Event();cancelled=threading.Event()
os.close(write)
thread=threading.Thread(target=worker.monitor_client,args=(read,finished,cancelled.set))
thread.start();thread.join(2)
assert not thread.is_alive() and cancelled.is_set()
os.close(read)
''')

    def test_incomplete_and_oversized_packets_are_refused(self):
        self.isolated('''for packet in (b'{}',b'x'*(worker.MAX_REQUEST+1)+b'\\n'):
 read,write=os.pipe()
 def sender():
  try:os.write(write,packet)
  except BrokenPipeError:pass
  finally:os.close(write)
 thread=threading.Thread(target=sender);thread.start()
 try:worker.read_packet(read);raise AssertionError('Invalid packet accepted')
 except worker.InstallerError:pass
 finally:os.close(read)
 thread.join(2);assert not thread.is_alive()
''')


if __name__ == '__main__':unittest.main()
