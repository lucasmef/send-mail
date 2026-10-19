import pytest
from mailqueue.storage import Store
from mailqueue.importer import import_batch
from mailqueue.worker import Worker,pause
from mailqueue.transport import DeliveryError
from test_worker import Simulated
from fakes import Clock


def test_pause_resume_no_reset(configured,batch_file):
    directory,config=configured
    store=Store(directory); import_batch(store,config,batch_file)
    clock=Clock()
    class Pausing(Simulated):
        def send(self,message,event):
            super().send(message,event)
            pause(store,message['run_id'] or store.db.execute('SELECT id FROM runs').fetchone()[0])
    first=Pausing(); worker=Worker(store,first,config,clock)
    result=worker.run('pause','fictional-batch',2)
    assert result['state']=='paused' and len(first.sent)==1
    run=result['run_id']; active=result['active_seconds']
    store.close(); clock.sleep(10000)
    store=Store(directory); transport=Simulated()
    result=Worker(store,transport,config,clock).resume(run)
    assert result['messages_started']==2
    assert result['state']=='limit_reached'
    assert result['active_seconds']<active+100
    assert len(transport.sent)==1
    store.close()


def test_retry_wait_total_attempts_and_interval(configured,batch_file):
    directory,config=configured
    store=Store(directory); ids=import_batch(store,config,batch_file)['ids']
    store.db.execute("UPDATE messages SET state='cancelled' WHERE id!=?",(ids[0],))
    clock=Clock()
    class Retry(Simulated):
        def send(self,message,event):
            raise DeliveryError('TEMPORARY')
    result=Worker(store,Retry(),config,clock).run('retry','fictional-batch',1,max_seconds=10000)
    assert result['attempts_started']==5
    assert store.get_message(ids[0])['state']=='failed'
    times=[row[0] for row in store.db.execute('SELECT started_at FROM attempts ORDER BY started_at')]
    assert all(b-a>=gap for a,b,gap in zip(times,times[1:],[60,300,900,3600]))
    store.close()


def test_legacy_daily_budget_is_ignored(configured,batch_file):
    directory,config=configured
    store=Store(directory); import_batch(store,config,batch_file)
    clock=Clock(); transport=Simulated()
    config['daily_budget']=1
    result=Worker(store,transport,config,clock).run('quota','fictional-batch',3)
    assert result['state']=='completed'
    assert len(transport.sent)==3
    assert store.db.execute('SELECT count(*) FROM attempts WHERE submission_reserved_at IS NOT NULL').fetchone()[0]==3
    store.close()


def test_max_attempts_and_duration(configured,batch_file):
    directory,config=configured
    store=Store(directory); import_batch(store,config,batch_file)
    clock=Clock(); transport=Simulated()
    first=Worker(store,transport,config,clock).run('attempts','fictional-batch',3,max_attempts=1)
    assert first['state']=='limit_reached' and first['attempts_started']==1
    second=Worker(store,transport,config,clock).run('time','fictional-batch',3,max_seconds=5)
    assert second['state']=='limit_reached' and second['attempts_started']==0
    assert store.db.execute("SELECT count(*) FROM messages WHERE state='pending'").fetchone()[0]==2
    store.close()


def test_variable_delay_persists_between_runs(configured,batch_file,monkeypatch):
    directory,config=configured
    store=Store(directory); import_batch(store,config,batch_file)
    clock=Clock(); draws=iter([17,39,23])
    monkeypatch.setattr('mailqueue.worker.random.uniform',lambda a,b:next(draws))
    first=Worker(store,Simulated(),config,clock).run('first-gap','fictional-batch',1)
    store.close(); store=Store(directory)
    Worker(store,Simulated(),config,clock).run('second-gap','fictional-batch',2)
    rows=list(store.db.execute('SELECT started_at,finished_at,delay_seconds FROM attempts ORDER BY started_at'))
    assert [r['delay_seconds'] for r in rows]==[17,39,23]
    assert rows[1]['started_at']-rows[0]['finished_at']==17
    assert rows[2]['started_at']-rows[1]['finished_at']==39
    store.close()


def test_over_100_submissions_in_one_day(configured,batch_file):
    import json
    directory,config=configured
    data=json.loads(batch_file.read_text())
    data['messages']=[{**data['messages'][0],'external_id':str(i)} for i in range(101)]
    batch_file.write_text(json.dumps(data))
    store=Store(directory); import_batch(store,config,batch_file)
    clock=Clock(); transport=Simulated()
    result=Worker(store,transport,config,clock).run('101-items','fictional-batch',101,max_attempts=110,max_seconds=10000)
    assert len(transport.sent)==101
    assert result['counts']['sent']==101
    store.close()
