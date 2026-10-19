from email import message_from_bytes
from email.policy import default
import uuid
import pytest
from mailqueue.storage import Store
from mailqueue.importer import import_batch
from mailqueue.testing import send_test
from mailqueue.worker import Worker
from mailqueue.transport import SMTPTransport
from mailqueue.errors import QueueError
from test_smtp import Session
from fakes import Clock
from test_worker import Simulated


def test_idempotent_copy_and_destination(configured,batch_file,monkeypatch):
    directory,config=configured; store=Store(directory)
    source=import_batch(store,config,batch_file)['ids'][0]
    original=dict(store.get_message(source)); clock=Clock()
    monkeypatch.setattr('mailqueue.credentials.retrieve',lambda _:uuid.uuid4().hex)
    session=Session(); transport=SMTPTransport(config,lambda *args,**kwargs:session)
    result=send_test(store,config,transport,source,'test@example.com','test-key',clock)
    copy=result['message']; assert copy['state']=='sent'
    assert copy['message_id']!=original['message_id']
    assert dict(store.get_message(source))==original
    assert ('rcpt','test@example.com') in session.actions
    assert ('rcpt',original['recipient']) not in session.actions
    data=next(action[1] for action in session.actions if isinstance(action,tuple) and action[0]=='data')
    assert str(message_from_bytes(data,policy=default)['To'])=='test@example.com'
    assert copy['source_message_id']==source and copy['kind']=='test'
    count=len(session.actions)
    assert send_test(store,config,transport,source,'test@example.com','test-key',clock)['message']['id']==copy['id']
    assert len(session.actions)==count
    with pytest.raises(QueueError) as error:
        send_test(store,config,transport,source,'other@example.com','test-key',clock)
    assert error.value.code=='IDEMPOTENCY_CONFLICT'
    assert store.db.execute('SELECT count(*) FROM attempts WHERE submission_reserved_at IS NOT NULL').fetchone()[0]==1
    store.close()


@pytest.mark.parametrize('mode,state',[('4xx','retry_wait'),('disconnect','uncertain'),('5xx','failed')])
def test_single_attempt_including_uncertain(configured,batch_file,monkeypatch,mode,state):
    directory,config=configured; store=Store(directory)
    source=import_batch(store,config,batch_file)['ids'][0]
    monkeypatch.setattr('mailqueue.credentials.retrieve',lambda _:uuid.uuid4().hex)
    transport=SMTPTransport(config,lambda *args,**kwargs:Session(mode)); clock=Clock()
    result=send_test(store,config,transport,source,'test@example.com','single',clock)
    assert result['message']['state']==state
    assert result['run']['attempts_started']==1
    Worker(store,Simulated(),config,clock).resume(result['run']['run_id'])
    assert store.get_message(result['message']['id'])['attempt_count']==1
    Worker(store,Simulated(),config,clock).run('normal','fictional-batch',3)
    assert store.get_message(result['message']['id'])['attempt_count']==1
    assert store.db.execute('SELECT count(*) FROM attempts WHERE message_id=? AND submission_reserved_at IS NOT NULL',(result['message']['id'],)).fetchone()[0]==1
    store.close()


def test_no_local_quota_for_test_copies(configured,batch_file):
    directory,config=configured; store=Store(directory)
    source=import_batch(store,config,batch_file)['ids'][0]
    config['daily_budget']=1; clock=Clock()
    first=send_test(store,config,Simulated(),source,'test@example.com','quota-test',clock)
    assert first['message']['state']=='sent'
    second=send_test(store,config,Simulated(),source,'test@example.com','quota-test-2',clock)
    assert second['message']['state']=='sent'
    assert store.get_message(source)['state']=='pending'
    assert store.db.execute('SELECT count(*) FROM attempts WHERE submission_reserved_at IS NOT NULL').fetchone()[0]==2
    store.close()
