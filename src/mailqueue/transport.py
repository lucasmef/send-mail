class DeliveryError(Exception):
    def __init__(self, code, outcome="transient", block=False, smtp_code=None):
        super().__init__(code)
        self.code, self.outcome, self.block, self.smtp_code = code, outcome, block, smtp_code


# O adaptador SMTP é integrado em T11. Transportes de testes implementam
# send(message, event) e close(); event informa marcos antes da submissão.

import contextlib
import re
import smtplib
import ssl
import certifi
from . import credentials
from .errors import QueueError

from .config import smtp_settings


def classify(code, response, stage):
    # Não guardar texto de servidor: ele pode conter dados pessoais ou segredos.
    text=response.decode('ascii','ignore').lower() if isinstance(response,bytes) else ''
    if code==421 or any(token in text for token in ('quota','throttl','too many','rate limit','5.2.2','4.7.')):
        return DeliveryError('SMTP_THROTTLED',block=True,smtp_code=code)
    if stage=='sender':
        return DeliveryError('SENDER_REFUSED',block=True,smtp_code=code)
    return DeliveryError('SMTP_'+str(code),'transient' if 400<=code<500 else 'permanent',smtp_code=code)


class SMTPTransport:
    def __init__(self,config,factory=None):
        self.config=config
        self.host,self.port,self.security=smtp_settings(config)
        self.factory=factory or (smtplib.SMTP_SSL if self.security=="ssl" else smtplib.SMTP)
        self.smtp=None
        self.submitted=False

    def timeout(self,seconds):
        if self.smtp.sock is not None:
            self.smtp.sock.settimeout(seconds)

    def connect(self,event=lambda _:None):
        self.submitted=False
        try:
            context=ssl.create_default_context(cafile=certifi.where())
            options=dict(timeout=30,local_hostname='localhost')
            if self.security=='ssl': options['context']=context
            self.smtp=self.factory(self.host,self.port,**options)
            event('connected')
            code,response=self.smtp.ehlo()
            if code!=250: raise classify(code,response,'hello')
            if self.security=='starttls':
                if not self.smtp.has_extn('starttls'):
                    raise DeliveryError('TLS_REQUIRED',block=True)
                self.smtp.starttls(context=context)
                self.timeout(30)
                code,response=self.smtp.ehlo()
                if code!=250: raise classify(code,response,'hello')
            secret=credentials.retrieve(self.config['login'])
            try:
                self.smtp.login(self.config['login'],secret)
            finally:
                secret=None
            event('authenticated')
        except QueueError as error:
            raise DeliveryError(error.code,block=True)
        except smtplib.SMTPAuthenticationError as error:
            raise DeliveryError('AUTH_FAILED',block=True,smtp_code=error.smtp_code)
        except (ssl.SSLError,smtplib.SMTPNotSupportedError):
            raise DeliveryError('TLS_INVALID',block=True)
        except smtplib.SMTPResponseException as error:
            raise classify(error.smtp_code,error.smtp_error,'connect')
        except (OSError,smtplib.SMTPException):
            raise DeliveryError('CONNECTION_FAILED')

    def send(self,message,event):
        from .dkim_signing import sign_message
        self.submitted=False
        try:
            wire_bytes=sign_message(message,self.config)
        except QueueError as error:
            raise DeliveryError(error.code,block=True) from None
        message['wire_bytes'] = wire_bytes
        self.connect(event)
        try:
            self.timeout(30)
            code,response=self.smtp.mail(message['sender'])
            if code!=250: raise classify(code,response,'sender')
            code,response=self.smtp.rcpt(message['recipient'])
            if code not in (250,251): raise classify(code,response,'recipient')
            event('envelope_ready')
            self.timeout(300)
            # Persistir antes de chamar DATA: conservador mesmo antes do 354.
            event('submission_started')
            self.submitted=True
            code,response=self.smtp.data(wire_bytes)
            if code!=250: raise classify(code,response,'data')
            return code
        except DeliveryError:
            raise
        except smtplib.SMTPResponseException as error:
            raise classify(error.smtp_code,error.smtp_error,'data' if self.submitted else 'envelope')
        except (OSError,smtplib.SMTPException):
            raise DeliveryError('SMTP_DISCONNECTED','uncertain' if self.submitted else 'transient')

    def close(self):
        if self.smtp is not None:
            try:
                self.timeout(10)
                self.smtp.quit()
            finally:
                self.smtp.close()
                self.smtp=None


def doctor(store,config):
    from .composer import address, signatures
    address(config['sender']); address(config['login']); signatures(config)
    if store.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise QueueError('DATABASE_INVALID','Verificação do banco falhou.',4)
    transport=SMTPTransport(config)
    try:
        transport.connect()
        return dict(database='ok',keychain='ok',tls='verified',authentication='ok',host=transport.host,port=transport.port,sent=False)
    except DeliveryError as error:
        raise QueueError(error.code,'Diagnóstico SMTP falhou; verifique conexão, TLS e configuração.',4,error.outcome=='transient')
    finally:
        with contextlib.suppress(Exception): transport.close()
