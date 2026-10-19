import time
import json
import uuid
from email import message_from_bytes
from email.policy import SMTP
from email.utils import formatdate
from .composer import digest
from .errors import QueueError
from .importer import insert_message
from .queries import show


def copy_message(store, source, request, params, recipient=None, kind='normal'):
    existing=store.db.execute("SELECT id,params_hash FROM messages WHERE request_id=?",(request,)).fetchone()
    if existing:
        if existing['params_hash']!=digest(params):
            raise QueueError('IDEMPOTENCY_CONFLICT','Chave usada com outros parâmetros.',3)
        return existing['id'],False
    row=store.get_message(source)
    identity='m_'+uuid.uuid4().hex
    destination=recipient or row['recipient']
    mime=message_from_bytes(row['mime_bytes'],policy=SMTP)
    msgid='<'+uuid.uuid4().hex+'@'+row['sender'].split('@')[1]+'>'
    mime.replace_header('Message-ID',msgid)
    if recipient is not None:
        mime.replace_header('To',destination)
    mime.replace_header('Date',formatdate(localtime=False))
    now=time.time()
    values={key:row[key] for key in ('batch_id','account_id','input_hash','sender','subject','html','text')}
    values.update(id=identity,external_id=identity,content_hash=digest([str(mime['From']),str(mime['To']),row['subject'],row['html'],row['text']]),recipient=destination,mime_bytes=mime.as_bytes(),message_id=msgid,kind=kind,source_message_id=source,request_id=request,params_hash=digest(params),created_at=now,updated_at=now)
    insert_message(store,values)
    return identity,True


def resolve(store,identity,action,reason,request=None):
    if not isinstance(reason,str) or not reason.strip():
        raise QueueError('REASON_REQUIRED','Informe motivo da decisão manual.')
    if action=='resend' and not request:
        raise QueueError('REQUEST_REQUIRED','Reenvio exige --request-id.')
    params=['resend',identity,reason]
    with store.transaction():
        if action=='resend':
            existing=store.db.execute('SELECT id,params_hash FROM messages WHERE request_id=?',(request,)).fetchone()
            if existing:
                if existing['params_hash']!=digest(params):
                    raise QueueError('IDEMPOTENCY_CONFLICT','Chave usada com outros parâmetros.',3)
                return show(store,existing['id'])
        row=store.get_message(identity)
        if row['state']!='uncertain':
            raise QueueError('INVALID_STATE','Resolução exige mensagem uncertain.',3)
        now=time.time()
        history=json.loads(row['resolution_history_json'])
        entry=dict(action=action,reason=reason,at=now)
        if action=='resend': entry['request_id']=request
        history.append(entry)
        store.db.execute('UPDATE messages SET resolution_history_json=? WHERE id=?',(json.dumps(history,ensure_ascii=False),identity))
        if action=='resend':
            new,_=copy_message(store,identity,request,params)
            store.db.execute('UPDATE messages SET resolution_action=?,resolution_reason=?,resolved_at=?,updated_at=? WHERE id=?',(action,reason,now,now,identity))
            return show(store,new)
        if action not in ('cancel','mark-sent'):
            raise QueueError('INVALID_ACTION','Ação inválida.')
        store.db.execute("UPDATE messages SET state=?,confirmation_source=?,sent_at=?,resolution_action=?,resolution_reason=?,resolved_at=?,updated_at=? WHERE id=?",('sent' if action=='mark-sent' else 'cancelled','manual' if action=='mark-sent' else None,now if action=='mark-sent' else None,action,reason,now,now,identity))
    return show(store,identity)
