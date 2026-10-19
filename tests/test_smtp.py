import smtplib
import ssl
import uuid
import pytest
from mailqueue import credentials
from mailqueue.transport import SMTPTransport,DeliveryError,doctor
from mailqueue.storage import Store
from mailqueue.importer import import_batch
from mailqueue.worker import Worker
from fakes import Clock


class Session:
    def __init__(self,mode='ok'):
        self.mode=mode; self.actions=[]; self.sock=self
    def settimeout(self,value): self.actions.append(('timeout',value))
    def ehlo(self): self.actions.append('ehlo'); return 250,b'ok'
    def has_extn(self,name): return self.mode!='no_tls'
    def starttls(self,context):
        assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
        self.actions.append('tls')
        if self.mode=='certificate': raise ssl.SSLCertVerificationError('invalid')
    def login(self,*args):
        assert 'tls' in self.actions
        self.actions.append('auth')
        if self.mode=='auth': raise smtplib.SMTPAuthenticationError(535,b'private')
    def mail(self,sender):
        self.actions.append(('mail',sender))
        return (550,b'refused') if self.mode=='sender' else (250,b'ok')
    def rcpt(self,recipient):
        self.actions.append(('rcpt',recipient))
        return (550,b'bad') if self.mode=='recipient' else (250,b'ok')
    def data(self,content):
        self.actions.append(('data',content))
        if self.mode=='disconnect': raise smtplib.SMTPServerDisconnected('private')
        if self.mode=='4xx': raise smtplib.SMTPDataError(451,b'temporary')
        if self.mode=='5xx': return 554,b'rejected'
        if self.mode=='quota': return 452,b'quota exceeded'
        return 250,b'accepted'
    def quit(self):
        self.actions.append('quit')
        if self.mode=='quit': raise OSError('quit')
    def close(self): self.actions.append('close')


@pytest.mark.parametrize('mode,state,blocked',[('ok','sent',False),('quit','sent',False),('4xx','retry_wait',False),('5xx','failed',False),('recipient','failed',False),('sender','retry_wait',True),('auth','retry_wait',True),('certificate','retry_wait',True),('no_tls','retry_wait',True),('disconnect','uncertain',False),('quota','retry_wait',True)])
def test_smtp_session(configured,batch_file,monkeypatch,mode,state,blocked):
    directory,config=configured
    store=Store(directory); ids=import_batch(store,config,batch_file)['ids']
    store.db.execute("UPDATE messages SET state='cancelled' WHERE id!=?",(ids[0],))
    opaque=uuid.uuid4().hex
    monkeypatch.setattr(credentials,'retrieve',lambda _:opaque)
    session=Session(mode)
    transport=SMTPTransport(config,lambda *args,**kwargs:session)
    result=Worker(store,transport,config,Clock()).run('smtp','fictional-batch',1,max_attempts=1)
    assert store.get_message(ids[0])['state']==state
    assert (result['state']=='blocked')==blocked
    if mode in ('auth','certificate','no_tls','sender','recipient'):
        assert not any(isinstance(a,tuple) and a[0]=='data' for a in session.actions)
    if mode in ('certificate','no_tls'):
        assert 'auth' not in session.actions
    if state=='uncertain':
        assert store.db.execute('SELECT phase FROM attempts').fetchone()[0]=='submission_started'
    assert opaque not in str([dict(r) for r in store.db.execute('SELECT * FROM attempts')])
    store.close()


def test_doctor_no_envelope(configured,monkeypatch):
    directory,config=configured; store=Store(directory)
    session=Session()
    monkeypatch.setattr('mailqueue.transport.smtplib.SMTP',lambda *args,**kwargs:session)
    monkeypatch.setattr(credentials,'retrieve',lambda _:uuid.uuid4().hex)
    assert doctor(store,config)['sent'] is False
    assert not any(isinstance(a,tuple) and a[0] in ('mail','rcpt','data') for a in session.actions)
    assert store.db.execute('SELECT count(*) FROM attempts').fetchone()[0]==0
    store.close()
