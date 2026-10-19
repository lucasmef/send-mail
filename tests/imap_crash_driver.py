import contextlib
import os
from pathlib import Path
import sys
from mailqueue.archiving import retry_archive
from mailqueue.config import load_config
from mailqueue.storage import Store
from mailqueue.worker import worker_lock

directory,identity,stage=Path(sys.argv[1]),sys.argv[2],sys.argv[3]
store=Store(directory)
class Remote:
    def connect(self): pass
    def select(self, folder): return '123'
    def find(self, mid):
        if stage=='before_append': os._exit(77)
        return []
    def append(self, folder, wire, sent_at):
        if stage=='after_reservation': os._exit(77)
        path=directory/'remote.eml'
        with path.open('wb') as stream:
            stream.write(wire); stream.flush(); os.fsync(stream.fileno())
        if stage=='after_append': os._exit(77)
        return 'OK',[b'']
    def close(self): pass
if stage=='before_commit':
    original=store.transaction
    @contextlib.contextmanager
    def transaction():
        with original():
            yield
            if store.db.execute('SELECT state FROM archives WHERE message_id=?',(identity,)).fetchone()[0]=='archived':
                os._exit(77)
    store.transaction=transaction
with worker_lock(directory): retry_archive(store,load_config(directory),identity,Remote())
