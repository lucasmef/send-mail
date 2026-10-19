import json
import os
from pathlib import Path
import sys
import tempfile
import uuid
from .composer import address, digest, to_text, header
from .config import prepare_dir, load_config, SMTP_PROVIDERS
from .errors import QueueError
from . import credentials


def prompt(label):
    print(label+': ',file=sys.stderr,end='',flush=True)
    return input().strip()


def atomic_private(path, content):
    fd,name=tempfile.mkstemp(prefix='.setup-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(name,path)
        directory_fd=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    finally:
        if os.path.exists(name): os.unlink(name)


def setup(directory, sender=None, provider=None, email=None, sender_name=None, replace_account=False):
    from .worker import worker_lock
    prepare_dir(directory)
    with worker_lock(directory):
        return _setup(directory,sender,provider,email,sender_name,replace_account)


def _setup(directory, sender, provider, email, sender_name, replace_account):
    prepare_dir(directory)
    previous=load_config(directory) if (directory/'config.json').exists() else None
    provider=provider or (previous or {}).get('provider','icloud')
    if provider not in SMTP_PROVIDERS:
        raise QueueError('CONFIG_INVALID','Provedor SMTP inválido.',4)
    login=address(email if email is not None else prompt('E-mail'))
    if sender_name is not None: sender_name=header(sender_name,'sender_name').strip()
    if sender is not None:
        sender=address(sender)
    account='a_'+digest(login if provider=='icloud' else [provider,login])[:24]
    existing=None
    if (directory/'config.json').exists():
        existing=load_config(directory)
        if existing.get('account_id')!=account and not replace_account:
            raise QueueError('ACCOUNT_CONFLICT','Este diretório já pertence a outra conta. Use outro diretório local.',3)
    # Nenhum segredo aparece em arquivo, argumento ou saída.
    print(f"Configurando {'KingHost' if provider == 'kinghost' else 'iCloud'}: {login}", file=sys.stderr)
    secret=credentials.secure_password(provider)
    try:
        if not secret:
            raise QueueError('CREDENTIAL_MISSING','Segredo vazio; configuração não gravada.',4)
        credentials.save(login,secret)
    finally:
        secret=None
    config=existing or dict(schema_version=1,account_id=account,login=login,sender=login,
                signature_html=str(directory/'signature.html'),signature_text=str(directory/'signature.txt'),
                interval_min_seconds=15,interval_max_seconds=45)
    if existing is not None and existing['account_id']!=account:
        config=dict(existing,account_id=account,login=login,sender=login)
        config.pop('dkim',None)
        config.pop('archive',None)
    config['provider']=provider
    if sender_name is not None: config['sender_name']=sender_name
    if sender is not None:
        config['sender']=sender
    if existing is None:
        atomic_private(directory/'signature.html',b'')
        atomic_private(directory/'signature.txt',b'')
    atomic_private(directory/'config.json',json.dumps(config,ensure_ascii=False,indent=2).encode())
    return dict(configured=True,account_id=account,sender=config['sender'])


def configure_signature(directory, html=None, text=None, clear=False):
    config=load_config(directory)
    if (clear and (html is not None or text is not None)) or (not clear and html is None):
        raise QueueError('INVALID_ARGUMENT','Use --html ARQUIVO [--text ARQUIVO] ou --clear.')
    try:
        content='' if clear else Path(html).expanduser().read_text(encoding='utf-8')
        plain='' if clear else (Path(text).expanduser().read_text(encoding='utf-8') if text is not None else to_text(content))
    except (OSError,ValueError):
        raise QueueError('SIGNATURE_MISSING','Não foi possível ler os arquivos UTF-8 de assinatura.',4)
    # Publicar os dois arquivos por uma única troca atômica da configuração.
    version=uuid.uuid4().hex
    html_path=directory/f'signature-{version}.html'
    text_path=directory/f'signature-{version}.txt'
    atomic_private(html_path,content.encode('utf-8'))
    atomic_private(text_path,plain.encode('utf-8'))
    config.update(signature_html=str(html_path),signature_text=str(text_path))
    atomic_private(directory/'config.json',json.dumps(config,ensure_ascii=False,indent=2).encode())
    return dict(signature_configured=bool(content or plain),applies_to='future_imports')


def configure_sender(directory, email=None, name=None):
    config=load_config(directory)
    if email is None and name is None:
        raise QueueError('INVALID_ARGUMENT','Informe --email e/ou --name.')
    if email is not None:
        config['sender']=address(email)
    if name is not None:
        config['sender_name']=header(name,'sender_name').strip()
    atomic_private(directory/'config.json',json.dumps(config,ensure_ascii=False,indent=2).encode())
    return dict(sender=config['sender'], sender_name=config.get('sender_name',''), applies_to='future_imports')
