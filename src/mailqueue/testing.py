"""Cópias de teste usam exclusivamente o worker e seu transporte SMTP."""
import uuid
from .composer import address, digest
from .errors import QueueError
from .queries import show
from .resolution import copy_message
from .worker import Worker,worker_lock,status


def existing_test(store,request,params):
    row=store.db.execute('SELECT id,params_hash,run_id FROM messages WHERE request_id=?',(request,)).fetchone()
    if row is None: return None
    if row['params_hash']!=digest(params):
        raise QueueError('IDEMPOTENCY_CONFLICT','Chave de teste usada com outros parâmetros.',3)
    return dict(message=show(store,row['id']),run=status(store,row['run_id']))


def send_test(store,config,transport,source,recipient,request,clock=None):
    recipient=address(recipient)
    if not request: raise QueueError('REQUEST_REQUIRED','Informe --request-id.')
    params=['test',source,recipient]
    existing=existing_test(store,request,params)
    if existing: return existing
    kwargs={} if clock is None else dict(clock=clock)
    worker=Worker(store,transport,config,**kwargs)
    with worker_lock(store.path.parent):
        store.ensure_sendable()
        worker.recover()
        with store.transaction():
            existing=existing_test(store,request,params)
            if existing: return existing
            original=store.get_message(source)
            if original['account_id']!=config['account_id']:
                raise QueueError('ACCOUNT_CONFLICT','Mensagem pertence a outra conta.',3)
            message,_=copy_message(store,source,request,params,recipient,'test')
            identity='r_'+uuid.uuid4().hex
            now=worker.clock.time()
            store.db.execute("INSERT INTO runs(id,request_id,params_hash,batch_id,state,max_messages,max_attempts,max_active_seconds,created_at,updated_at,test_message_id) VALUES(?,?,?,?,'running',1,1,3600,?,?,?)",(identity,'__test__:'+request,digest(params),original['batch_id'],now,now,message))
            store.db.execute('UPDATE messages SET run_id=? WHERE id=?',(identity,message))
        worker.process(identity)
        return existing_test(store,request,params)
