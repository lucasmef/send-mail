"""DKIM opcional: segredo somente em memória e no Keychain nativo."""
import base64
import json
import re
import subprocess
import uuid
from email import policy
from email.parser import BytesParser
import dkim
from . import credentials
from .errors import QueueError

SERVICE = 'SendMail.dkim.v1'
HEADERS = [b'from', b'to', b'subject', b'date', b'message-id',
           b'mime-version', b'content-type', b'content-transfer-encoding', b'from']


def validate(settings):
    if not isinstance(settings, dict) or set(settings) != {'domain','selector','record','enabled'}:
        raise QueueError('DKIM_CONFIG_INVALID','Configuração DKIM inválida.',4)
    if type(settings['enabled']) is not bool or not all(isinstance(settings[k],str) for k in ('domain','selector','record')):
        raise QueueError('DKIM_CONFIG_INVALID','Configuração DKIM inválida.',4)
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',settings['selector']):
        raise QueueError('DKIM_CONFIG_INVALID','Seletor DKIM inválido.',4)
    labels=settings['domain'].split('.')
    if len(labels)<2 or len(settings['domain'])>253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',x) for x in labels):
        raise QueueError('DKIM_CONFIG_INVALID','Domínio DKIM inválido.',4)
    if not re.fullmatch(r'v=DKIM1; k=rsa; p=[A-Za-z0-9+/=]+',settings['record']):
        raise QueueError('DKIM_CONFIG_INVALID','Registro DKIM inválido.',4)


def identity(settings):
    return settings['selector']+'._domainkey.'+settings['domain']


def generate_key():
    try:
        key=subprocess.run(['/usr/bin/openssl','genrsa','2048'],capture_output=True,check=True,timeout=30).stdout
        public=subprocess.run(['/usr/bin/openssl','rsa','-pubout','-outform','DER'],input=key,capture_output=True,check=True,timeout=10).stdout
        return key.decode('ascii'),'v=DKIM1; k=rsa; p='+base64.b64encode(public).decode('ascii')
    except Exception:
        raise QueueError('DKIM_KEY_ERROR','Não foi possível gerar a chave DKIM.',4) from None


def private_key(settings):
    try:
        value=credentials.native_backend().get_password(SERVICE,identity(settings))
        if not value: raise ValueError()
        return value.encode('ascii')
    except Exception:
        raise QueueError('DKIM_KEY_ERROR','Chave DKIM indisponível nas Chaves do macOS.',4) from None


def sign_bytes(raw,settings):
    validate(settings)
    secret=private_key(settings)
    try:
        signature=dkim.sign(raw,settings['selector'].encode(),settings['domain'].encode(),secret,
                            signature_algorithm=b'rsa-sha256',canonicalize=(b'relaxed',b'relaxed'),
                            include_headers=HEADERS)
        signed=signature+raw
        if not dkim.verify(signed,dnsfunc=lambda *a,**k:settings['record'].encode()):
            raise ValueError()
        return signed
    except Exception:
        raise QueueError('DKIM_SIGN_FAILED','Não foi possível validar a assinatura DKIM local.',4) from None
    finally:
        secret=None


def sign_message(message,config):
    settings=config.get('dkim')
    if settings is None: return message['mime_bytes']
    validate(settings)
    if not settings['enabled']:
        raise QueueError('DKIM_NOT_ENABLED','Publique o TXT e execute dkim enable, ou desative com dkim disable.',4)
    raw=message['mime_bytes']
    parsed=BytesParser(policy=policy.default).parsebytes(raw,headersonly=True)
    try:
        headers=parsed.get_all('From',[])
        addresses=headers[0].addresses
        if len(headers)!=1 or len(addresses)!=1 or addresses[0].domain.lower()!=settings['domain'] or message['sender'].rsplit('@',1)[1].lower()!=settings['domain']:
            raise ValueError()
    except Exception:
        raise QueueError('DKIM_CONFIG_INVALID','Domínio do remetente difere da configuração DKIM.',4) from None
    return sign_bytes(raw,settings)


def configure(directory,action):
    from .worker import worker_lock
    from .config import load_config
    from .setup import atomic_private
    with worker_lock(directory):
        config=load_config(directory)
        settings=config.get('dkim')
        if action=='disable':
            config.pop('dkim',None)
            atomic_private(directory/'config.json',json.dumps(config,ensure_ascii=False,indent=2).encode())
            return {'configured':False,'enabled':False}
        if action=='setup' and settings is None:
            key,record=generate_key()
            settings=dict(domain=config['sender'].rsplit('@',1)[1].lower(),selector='mq'+uuid.uuid4().hex[:12],record=record,enabled=False)
            validate(settings)
            try:
                credentials.native_backend().set_password(SERVICE,identity(settings),key)
            except Exception:
                raise QueueError('DKIM_KEY_ERROR','Não foi possível salvar a chave no Keychain.',4) from None
            finally:
                key=None
            config['dkim']=settings
            atomic_private(directory/'config.json',json.dumps(config,ensure_ascii=False,indent=2).encode())
        if settings is None:
            if action=='status': return {'configured':False,'enabled':False}
            raise QueueError('DKIM_CONFIG_INVALID','Execute dkim setup primeiro.',4)
        validate(settings)
        if action=='enable':
            raw=('From: <'+config['sender']+'>\r\nTo: <'+config['sender']+'>\r\nSubject: DKIM local\r\n\r\nVerificacao sem envio.\r\n').encode()
            signed=sign_message({'sender':config['sender'],'mime_bytes':raw},dict(config,dkim=dict(settings,enabled=True)))
            try:
                valid=dkim.verify(signed,timeout=10)
            except Exception:
                valid=False
            if not valid:
                raise QueueError('DKIM_DNS_INVALID','TXT DKIM ausente, incompatível ou DNS indisponível; ativação não concluída.',4)
            settings['enabled']=True
            atomic_private(directory/'config.json',json.dumps(config,ensure_ascii=False,indent=2).encode())
        return dict(configured=True,enabled=settings['enabled'],type='TXT',host=settings['selector']+'._domainkey',fqdn=identity(settings),value=settings['record'])
