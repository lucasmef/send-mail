"""Processo descartável com transporte simulado; não importa SMTP/Keychain."""
import json
import sys
import time
from pathlib import Path
from mailqueue.storage import Store
from mailqueue.worker import Worker

root,stage,ready=Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3])
store=Store(root)
config=json.loads((root/'config.json').read_text())
def stop():
    ready.write_text('ready')
    time.sleep(30)
class Simulated:
    def send(self,message,event):
        if stage in ('reserved','sigint'):
            if stage=='sigint':
                ready.write_text('ready'); time.sleep(0.3)
            else: stop()
        event('connected'); event('authenticated'); event('envelope_ready')
        event('submission_started')
        if stage=='submission': stop()
    def close(self):
        if stage=='persisted': stop()
        if stage=='quit_error': raise OSError('quit')
worker=Worker(store,Simulated(),config)
if stage=='accepted':
    worker.accept=lambda *args:stop()
worker.run('crash','fictional-batch',3)
