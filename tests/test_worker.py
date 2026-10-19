import json
import subprocess
import sys
import pytest
from mailqueue.storage import Store
from mailqueue.importer import import_batch
from mailqueue.worker import Worker, worker_lock
from mailqueue.errors import QueueError
from fakes import Clock


class Simulated:
    def __init__(self):
        self.sent=[]
    def send(self,message,event):
        for phase in ("connected","authenticated","envelope_ready","submission_started"):
            event(phase)
        self.sent.append(message["id"])
    def close(self):
        pass


def test_worker_idempotent(configured,batch_file):
    directory,config=configured
    store=Store(directory)
    import_batch(store,config,batch_file)
    transport=Simulated(); worker=Worker(store,transport,config,Clock())
    result=worker.run("key-1","fictional-batch",2)
    assert result["counts"]["sent"]==2
    assert result["state"]=="limit_reached"
    assert len(transport.sent)==2
    repeated=worker.run("key-1","fictional-batch",2)
    assert repeated["run_id"]==result["run_id"]
    assert len(transport.sent)==2
    with pytest.raises(QueueError) as error:
        worker.run("key-1","fictional-batch",3)
    assert error.value.code=="IDEMPOTENCY_CONFLICT"
    assert store.db.execute("SELECT count(*) FROM attempts").fetchone()[0]==2
    store.close()


def test_lock_between_processes(configured):
    directory,_=configured
    script="from pathlib import Path; from mailqueue.worker import worker_lock; from mailqueue.errors import QueueError; import sys;\ntry:\n with worker_lock(Path(sys.argv[1])): print('entered')\nexcept QueueError as e: print(e.code); sys.exit(e.exit_code)"
    with worker_lock(directory):
        result=subprocess.run([sys.executable,"-c",script,str(directory)],capture_output=True,text=True)
        assert result.returncode==6
        assert result.stdout.strip()=="WORKER_BUSY"
    with worker_lock(directory):
        pass
