import json
import ssl
import uuid
import pytest
from mailqueue import credentials
from mailqueue.setup import setup
from mailqueue.config import load_config
from mailqueue.transport import SMTPTransport, DeliveryError, doctor
from mailqueue.storage import Store
from mailqueue.importer import import_batch
from mailqueue.worker import Worker
from mailqueue.errors import QueueError
from test_smtp import Session
from test_worker import Simulated
from fakes import Clock


def test_switch_account_preserves_history_and_uses_only_new_queue(configured,batch_file,monkeypatch):
    directory,old=configured
    store=Store(directory); ids=import_batch(store,old,batch_file)['ids']
    monkeypatch.setattr(credentials,'secure_password',lambda *args:uuid.uuid4().hex)
    saved=[]
    monkeypatch.setattr(credentials,'save',lambda login,secret:saved.append(login))
    with pytest.raises(QueueError):
        setup(directory,provider='kinghost',email='contact@example.com')
    assert saved==[]
    setup(directory,provider='kinghost',email='contact@example.com',sender_name='Equipe',replace_account=True)
    config=load_config(directory)
    assert config['login']==config['sender']=='contact@example.com'
    assert config['provider']=='kinghost' and saved==['contact@example.com']
    assert config['signature_html']==old['signature_html']
    transport=Simulated()
    Worker(store,transport,config,Clock()).run('new-account','fictional-batch',3)
    assert transport.sent==[]
    assert all(store.get_message(i)['state']=='pending' for i in ids)
    store.close()


def test_kinghost_ssl_and_doctor_no_send(configured,monkeypatch):
    directory,config=configured; config['provider']='kinghost'
    session=Session(); session.actions.append('tls')
    def factory(host,port,**kw):
        assert (host,port)==('smtp.kinghost.net',465)
        assert kw['context'].check_hostname
        assert kw['context'].verify_mode==ssl.CERT_REQUIRED
        return session
    monkeypatch.setattr('mailqueue.transport.smtplib.SMTP_SSL',factory)
    monkeypatch.setattr(credentials,'retrieve',lambda _:uuid.uuid4().hex)
    store=Store(directory)
    result=doctor(store,config)
    assert result['host']=='smtp.kinghost.net' and result['port']==465 and not result['sent']
    assert session.actions.count('tls')==1
    assert not any(isinstance(a,tuple) and a[0] in ('mail','rcpt','data') for a in session.actions)
    store.close()


def test_kinghost_bad_certificate_never_reads_secret(monkeypatch):
    def factory(*args,**kw): raise ssl.SSLCertVerificationError('bad')
    def forbidden(*args): raise AssertionError('credential access before TLS')
    monkeypatch.setattr(credentials,'retrieve',forbidden)
    with pytest.raises(DeliveryError) as error:
        SMTPTransport({'provider':'kinghost','login':'contact@example.com'},factory).connect()
    assert error.value.code=='TLS_INVALID'


@pytest.mark.parametrize('provider', ['icloud', 'kinghost'])
def test_tls_trust_works_without_system_bundle(tmp_path,monkeypatch,provider):
    empty=tmp_path/'empty.pem'; empty.write_text('')
    monkeypatch.setenv('SSL_CERT_FILE',str(empty))
    monkeypatch.setenv('SSL_CERT_DIR',str(tmp_path))
    seen=[]
    session=Session()
    def verify(context):
        assert context.check_hostname
        assert context.verify_mode==ssl.CERT_REQUIRED
        assert context.cert_store_stats()['x509_ca']>0
        seen.append(True)
    def starttls(*,context):
        verify(context)
        session.actions.append('tls')
    session.starttls=starttls
    def factory(*args,**kw):
        if provider=='kinghost':
            verify(kw['context'])
            session.actions.append('tls')
        return session
    monkeypatch.setattr(credentials,'retrieve',lambda _:uuid.uuid4().hex)
    SMTPTransport({'provider':provider,'login':'contact@example.com'},factory).connect()
    assert seen==[True]
