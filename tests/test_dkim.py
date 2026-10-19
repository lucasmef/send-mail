import json
import uuid
import dkim
import pytest
from mailqueue import credentials
from mailqueue.config import load_config
from mailqueue.dkim_signing import configure,sign_message,generate_key,SERVICE
from mailqueue.errors import QueueError
from mailqueue.transport import SMTPTransport,DeliveryError
from test_smtp import Session

RAW=(b'From: Example <sender@example.com>\r\nTo: Receiver <to@example.net>\r\n'
     b'Subject: Assunto\r\nDate: Wed, 30 Sep 2026 19:00:00 +0000\r\n'
     b'Message-ID: <test@example.com>\r\nMIME-Version: 1.0\r\n'
     b'Content-Type: text/plain; charset=utf-8\r\n\r\nConteudo original.\r\n')

@pytest.fixture
def prepared(configured,monkeypatch):
    directory,config=configured
    config['sender']='sender@example.com'
    (directory/'config.json').write_text(json.dumps(config))
    secrets={}
    class Backend:
        def set_password(self,service,login,secret): secrets[(service,login)]=secret
        def get_password(self,service,login): return secrets.get((service,login))
    monkeypatch.setattr(credentials,'native_backend',lambda:Backend())
    result=configure(directory,'setup')
    return directory,result,secrets


def test_setup_idempotent_private_only_in_keychain(prepared):
    directory,result,secrets=prepared
    assert result==configure(directory,'setup')
    assert len(secrets)==1 and next(iter(secrets))[0]==SERVICE
    assert 'PRIVATE' not in json.dumps(result)+(directory/'config.json').read_text()
    assert not result['enabled']
    assert result['value'].startswith('v=DKIM1; k=rsa; p=')


def test_signature_and_tampering(prepared):
    directory,result,_=prepared
    config=load_config(directory); config['dkim']['enabled']=True
    signed=sign_message({'sender':'sender@example.com','mime_bytes':RAW},config)
    verify=lambda data:dkim.verify(data,dnsfunc=lambda *a,**k:result['value'].encode())
    assert b'a=rsa-sha256' in signed and b'd=example.com' in signed
    assert signed.endswith(RAW) and verify(signed)
    assert verify(b'Received: from relay.example.net\r\n'+signed)
    assert not verify(signed.replace(b'Conteudo original',b'Conteudo alterado'))
    assert not verify(signed.replace(b'Subject: Assunto',b'Subject: Alterado'))
    assert not verify(signed.replace(b'From: Example',b'From: Outra'))


def test_dns_enable_requires_matching_key(prepared,monkeypatch):
    directory,result,_=prepared
    import dkim.dnsplug
    monkeypatch.setattr(dkim.dnsplug,'_get_txt',lambda *a,**k:None)
    with pytest.raises(QueueError) as e: configure(directory,'enable')
    assert e.value.code=='DKIM_DNS_INVALID'
    assert not load_config(directory)['dkim']['enabled']
    wrong_record=generate_key()[1]
    monkeypatch.setattr(dkim.dnsplug,'_get_txt',lambda *a,**k:wrong_record.encode())
    with pytest.raises(QueueError) as e: configure(directory,'enable')
    assert e.value.code=='DKIM_DNS_INVALID'
    monkeypatch.setattr(dkim.dnsplug,'_get_txt',lambda *a,**k:result['value'].encode())
    assert configure(directory,'enable')['enabled']
    assert configure(directory,'disable')=={'configured':False,'enabled':False}
    assert sign_message({'mime_bytes':RAW},load_config(directory))==RAW


@pytest.mark.parametrize('mode,code',[('pending','DKIM_NOT_ENABLED'),('missing','DKIM_KEY_ERROR'),('domain','DKIM_CONFIG_INVALID'),('wrong_key','DKIM_SIGN_FAILED')])
def test_failure_blocks_before_network(prepared,mode,code):
    directory,_,secrets=prepared
    config=load_config(directory)
    if mode!='pending': config['dkim']['enabled']=True
    if mode=='missing': secrets.clear()
    if mode=='wrong_key': secrets[next(iter(secrets))]=generate_key()[0]
    raw=RAW.replace(b'sender@example.com',b'sender@other.example') if mode=='domain' else RAW
    def forbidden(*a,**k): raise AssertionError('network before DKIM validation')
    transport=SMTPTransport(config,forbidden)
    with pytest.raises(DeliveryError) as e:
        transport.send({'sender':'sender@example.com','mime_bytes':raw},lambda _:None)
    assert e.value.code==code and e.value.block
    assert not transport.submitted


def test_transport_sends_signed_mime(prepared,monkeypatch):
    directory,result,_=prepared
    config=load_config(directory); config['dkim']['enabled']=True
    session=Session()
    monkeypatch.setattr(credentials,'retrieve',lambda _:uuid.uuid4().hex)
    transport=SMTPTransport(config,lambda *a,**k:session)
    transport.send({'sender':'sender@example.com','recipient':'to@example.net','mime_bytes':RAW},lambda _:None)
    data=[x[1] for x in session.actions if isinstance(x,tuple) and x[0]=='data'][0]
    assert dkim.verify(data,dnsfunc=lambda *a,**k:result['value'].encode())
