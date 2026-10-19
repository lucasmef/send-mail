"""CLI real em processo separado; rede/credenciais/relógio são substituídos só aqui."""
import sys
import time
import uuid
from pathlib import Path
from fakes import Clock
from test_smtp import Session
from mailqueue import cli,credentials,transport,worker
from mailqueue.storage import Store

scenario=sys.argv[1]
arguments=sys.argv[2:]
original_worker=worker.Worker
class ControlledWorker(original_worker):
    def __init__(self,store,adapter,config,**kwargs):
        super().__init__(store,adapter,config,Clock(time.time()))
worker.Worker=ControlledWorker
credentials.retrieve=lambda _:uuid.uuid4().hex
class SimulatedSession(Session):
    def __init__(self): super().__init__('auth' if scenario=='auth' else 'ok')
    def data(self,content):
        if scenario=='pause':
            directory=Path(arguments[arguments.index('--data-dir')+1])
            store=Store(directory)
            run=store.db.execute("SELECT run_id FROM messages WHERE state='sending'").fetchone()[0]
            worker.pause(store,run); store.close()
        return super().data(content)
transport.smtplib.SMTP=lambda *args,**kwargs:SimulatedSession()
raise SystemExit(cli.main(arguments))
