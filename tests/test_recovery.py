import signal
import subprocess
import sys
import time
from pathlib import Path
import pytest
from mailqueue.storage import Store
from mailqueue.importer import import_batch
from mailqueue.worker import Worker
from mailqueue.resolution import resolve
from test_worker import Simulated
from fakes import Clock


@pytest.mark.parametrize('stage,expected',[('reserved','sent'),('submission','uncertain'),('accepted','uncertain'),('persisted','sent')])
def test_kill_at_phases(configured,batch_file,tmp_path,stage,expected):
    directory,config=configured
    store=Store(directory); ids=import_batch(store,config,batch_file)['ids']
    store.db.execute("UPDATE messages SET state='cancelled' WHERE id!=?",(ids[0],)); store.close()
    ready=tmp_path/'ready'
    proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('crash_driver.py')),str(directory),stage,str(ready)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+10
        while not ready.exists() and time.monotonic()<deadline and proc.poll() is None:
            time.sleep(0.01)
        assert ready.exists(),proc.communicate(timeout=1)
        proc.kill(); proc.communicate(timeout=5)
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()
    store=Store(directory)
    run=store.db.execute('SELECT id FROM runs').fetchone()[0]
    transport=Simulated()
    result=Worker(store,transport,config,Clock(time.time()+20)).resume(run)
    assert store.get_message(ids[0])['state']==expected
    assert len(transport.sent)==(1 if stage=='reserved' else 0)
    assert result['history']['attempts']==(2 if stage=='reserved' else 1)
    assert store.db.execute('SELECT count(*) FROM attempts WHERE submission_reserved_at IS NOT NULL').fetchone()[0]==1
    store.close()


def test_sigint_cooperative(configured,batch_file,tmp_path):
    directory,config=configured
    store=Store(directory); import_batch(store,config,batch_file); store.close()
    ready=tmp_path/'ready'
    proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('crash_driver.py')),str(directory),'sigint',str(ready)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+10
        while not ready.exists() and time.monotonic()<deadline:
            time.sleep(0.01)
        assert ready.exists()
        proc.send_signal(signal.SIGINT)
        out,err=proc.communicate(timeout=5)
        assert proc.returncode==0,(out,err)
        store=Store(directory)
        run=store.db.execute('SELECT * FROM runs').fetchone()
        assert run['state']=='paused' and run['pause_requested']==1
        assert store.db.execute("SELECT count(*) FROM messages WHERE state='sent'").fetchone()[0]==1
        store.close()
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()


def test_success_persist_failure_stops_and_quit_keeps_sent(configured,batch_file,monkeypatch):
    directory,config=configured
    store=Store(directory); ids=import_batch(store,config,batch_file)['ids']
    transport=Simulated(); worker=Worker(store,transport,config,Clock())
    def cannot_record(*args): raise OSError('disco indisponível')
    monkeypatch.setattr(worker,'accept',cannot_record)
    with pytest.raises(OSError): worker.run('disk','fictional-batch',3)
    assert len(transport.sent)==1
    run=store.db.execute('SELECT id FROM runs').fetchone()[0]
    new=Simulated()
    result=Worker(store,new,config,Clock()).resume(run)
    assert result['counts']['uncertain']==1
    assert len(new.sent)==2
    uncertain=store.db.execute("SELECT id FROM messages WHERE state='uncertain'").fetchone()[0]
    resend=resolve(store,uncertain,'resend','Usuário autorizou nova cópia','manual-copy')
    assert resend['state']=='pending' and resend['source_message_id']==uncertain
    assert resend['message_id']!=store.get_message(uncertain)['message_id']
    assert resolve(store,uncertain,'resend','Usuário autorizou nova cópia','manual-copy')['id']==resend['id']
    marked=resolve(store,uncertain,'mark-sent','Recebimento confirmado')
    assert marked['confirmation_source']=='manual'
    class BadQuit(Simulated):
        def close(self): raise OSError('quit')
    Worker(store,BadQuit(),config,Clock()).run('quit','fictional-batch',10)
    assert store.get_message(resend['id'])['state']=='sent'
    store.close()
