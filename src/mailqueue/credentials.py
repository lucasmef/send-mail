import getpass
import sys
from .errors import QueueError

SERVICE = 'SendMail.mailqueue.v1'


def native_backend():
    if sys.platform != 'darwin':
        raise QueueError('KEYCHAIN_UNAVAILABLE','O backend nativo das Chaves exige macOS.',4)
    try:
        from keyring.backends.macOS import Keyring
        backend=Keyring()
        backend.keychain=None
        if backend.priority<=0:
            raise RuntimeError()
        return backend
    except Exception:
        raise QueueError('KEYCHAIN_UNAVAILABLE','Backend nativo das Chaves indisponível; nenhum fallback permitido.',4)


def secure_password(provider="icloud"):
    if not sys.stdin.isatty():
        raise QueueError('TTY_REQUIRED','Execute setup em um terminal para informar o segredo sem eco.',4)
    label = 'Senha da caixa de e-mail KingHost (sem eco): ' if provider == 'kinghost' else 'Senha de aplicativo do iCloud (sem eco): '
    return getpass.getpass(label)


def save(login, secret):
    try:
        native_backend().set_password(SERVICE,login,secret)
    except QueueError:
        raise
    except Exception:
        raise QueueError('KEYCHAIN_DENIED','As Chaves estão bloqueadas ou o acesso foi negado.',4)


def retrieve(login):
    try:
        secret=native_backend().get_password(SERVICE,login)
    except QueueError:
        raise
    except Exception:
        raise QueueError('KEYCHAIN_DENIED','As Chaves estão bloqueadas ou o acesso foi negado.',4)
    if not secret:
        raise QueueError('CREDENTIAL_MISSING','Credencial não encontrada; execute setup localmente.',4)
    return secret
