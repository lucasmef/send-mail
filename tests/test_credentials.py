import json
import uuid
import pytest
from mailqueue import credentials
from mailqueue.errors import QueueError
from mailqueue.setup import setup


def test_native_only(monkeypatch):
    monkeypatch.setattr(credentials.sys,'platform','linux')
    with pytest.raises(QueueError) as error: credentials.native_backend()
    assert error.value.code=='KEYCHAIN_UNAVAILABLE'


@pytest.mark.parametrize('mode',['denied','locked','missing'])
def test_keychain_sanitized(monkeypatch,capsys,mode):
    opaque=uuid.uuid4().hex
    class Backend:
        def get_password(self,*args):
            if mode=='missing': return None
            raise RuntimeError(opaque)
    monkeypatch.setattr(credentials,'native_backend',lambda:Backend())
    with pytest.raises(QueueError) as error: credentials.retrieve('fictional@icloud.com')
    assert opaque not in str(error.value) and opaque not in json.dumps(error.value.as_dict())
    assert opaque not in str(capsys.readouterr())


def test_setup_no_secret_files_or_output(tmp_path,monkeypatch,capsys):
    responses=iter(['fictional@icloud.com'])
    monkeypatch.setattr('builtins.input',lambda:next(responses))
    opaque=uuid.uuid4().hex
    monkeypatch.setattr(credentials,'secure_password',lambda *args:opaque)
    saved=[]
    class Backend:
        def set_password(self,service,login,secret): saved.append((service,login,secret))
    monkeypatch.setattr(credentials,'native_backend',lambda:Backend())
    root=tmp_path/'data'; result=setup(root)
    assert saved[0][2]==opaque
    assert opaque not in json.dumps(result)
    assert opaque not in str(capsys.readouterr())
    for file in root.iterdir():
        assert opaque not in file.read_text()
        assert file.stat().st_mode & 0o777==0o600
    assert json.loads((root/'config.json').read_text())['sender']=='fictional@icloud.com'
    from mailqueue.composer import compose
    from mailqueue.config import load_config
    item=dict(external_id='one', to='person@example.com',subject='Teste',html='<p>Olá</p>')
    assert compose(item,load_config(root))['html']=='<p>Olá</p>'


def test_no_tty_fallback(monkeypatch):
    monkeypatch.setattr(credentials.sys.stdin,'isatty',lambda:False)
    with pytest.raises(QueueError) as error: credentials.secure_password()
    assert error.value.code=='TTY_REQUIRED'


@pytest.mark.parametrize('priority',[0,None])
def test_native_backend_unavailable_no_fallback(monkeypatch,priority):
    import keyring.backends.macOS as native
    class Unavailable:
        keychain=None
        @property
        def priority(self):
            if priority is None: raise RuntimeError('API indisponível')
            return priority
    monkeypatch.setattr(credentials.sys,'platform','darwin')
    monkeypatch.setattr(native,'Keyring',Unavailable)
    monkeypatch.setenv('PYTHON_KEYRING_BACKEND','keyring.backends.fail.Keyring')
    with pytest.raises(QueueError) as error: credentials.native_backend()
    assert error.value.code=='KEYCHAIN_UNAVAILABLE'


@pytest.mark.parametrize('provider,expected,absent', [('kinghost','KingHost','iCloud'),('icloud','iCloud','KingHost')])
def test_password_prompt_matches_provider(monkeypatch,provider,expected,absent):
    monkeypatch.setattr(credentials.sys.stdin,'isatty',lambda:True)
    labels=[]
    opaque=uuid.uuid4().hex
    monkeypatch.setattr(credentials.getpass,'getpass',lambda label: labels.append(label) or opaque)
    assert credentials.secure_password(provider)==opaque
    assert expected in labels[0] and absent not in labels[0]
