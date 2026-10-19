import contextlib
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
import uuid
import pytest
from mailqueue.archiving import IMAPArchive, configure, retry_archive, archive_status, quoted
from mailqueue.cli import main
from mailqueue.config import load_config
from mailqueue.errors import QueueError
from mailqueue.importer import import_batch
from mailqueue.storage import Store
from mailqueue.transport import SMTPTransport
from mailqueue.worker import Worker, worker_lock
from fakes import Clock
from test_worker import Simulated


class Session:
    def __init__(self, mode='ok', folders=None):
        self.mode = mode
        self.names = folders if folders is not None else [b'(\\HasNoChildren \\Sent) "." "INBOX.Outgoing Mail"']
        self.actions = []
        self.copies = []
        self.matches = []
    def login(self, *args): self.actions.append('login'); return 'OK', [b'']
    def list(self): self.actions.append('list'); return 'OK', self.names
    def select(self, folder, readonly):
        assert readonly
        self.actions.append(('select', folder))
        return 'OK', [b'0']
    def response(self, code): return code, [b'123']
    def uid(self, command, *args):
        self.actions.append((command, args))
        if command == 'SEARCH':
            return 'OK', [b' '.join(str(i+1).encode() for i in range(len(self.matches)))]
        return 'OK', [(b'HEADER', ('Message-ID: '+self.matches[int(args[0])-1]+'\r\n\r\n').encode())]
    def append(self, folder, flags, date, wire):
        self.actions.append(('append', folder, flags, date))
        if self.mode == 'reject': return 'NO', [b'private']
        self.copies.append(wire)
        if self.mode == 'disconnect': raise OSError('private')
        return 'OK', [b'accepted']
    def create(self, folder):
        self.actions.append(('create', folder))
        self.names.append(b'(\\HasNoChildren) "." '+folder.encode())
        return 'OK', [b'']
    def subscribe(self, folder): self.actions.append(('subscribe', folder)); return 'OK', [b'']
    def logout(self):
        if self.mode == 'logout': raise OSError('private')
        return 'BYE', [b'']


@pytest.fixture
def account(configured, monkeypatch):
    directory, config = configured
    config.update(provider='kinghost', archive=dict(folder='INBOX.Outgoing Mail'))
    (directory/'config.json').write_text(json.dumps(config))
    monkeypatch.setattr('mailqueue.credentials.retrieve', lambda _: uuid.uuid4().hex)
    return directory, config


def installed_session(monkeypatch, session):
    def factory(host, port, ssl_context, timeout):
        assert (host,port)==('imap.kinghost.net',993)
        assert ssl_context.check_hostname and ssl_context.verify_mode == ssl.CERT_REQUIRED
        return session
    monkeypatch.setattr('imaplib.IMAP4_SSL', factory)
    return factory


@pytest.mark.parametrize('mode,expected', [('ok','archived'),('reject','failed'),('disconnect','uncertain'),('logout','archived')])
def test_archive_after_commit_no_smtp_resend(account, batch_file, monkeypatch, mode, expected):
    directory, config = account
    store = Store(directory)
    ids=import_batch(store,config,batch_file)['ids']
    before=[tuple(row) for row in store.db.execute('SELECT * FROM messages WHERE id!=? ORDER BY id',(ids[0],))]
    session=Session(mode)
    original_append=session.append
    def append(*args):
        assert not store.db.in_transaction
        assert store.get_message(ids[0])['state']=='sent'
        assert archive_status(store,ids[0])['state']=='appending'
        return original_append(*args)
    session.append=append
    installed_session(monkeypatch,session)
    smtp=Simulated()
    result=Worker(store,smtp,config,Clock()).run('archive','fictional-batch',1,max_attempts=1)
    assert result['archives']=={expected:1}
    assert archive_status(store,ids[0])['state']==expected
    assert smtp.sent==[ids[0]]
    assert store.get_message(ids[0])['state']=='sent'
    assert before==[tuple(row) for row in store.db.execute('SELECT * FROM messages WHERE id!=? ORDER BY id',(ids[0],))]
    if mode=='reject':
        session.mode='ok'
        with worker_lock(directory): assert retry_archive(store,config,ids[0])['state']=='archived'
        assert len(session.copies)==1
    elif mode=='disconnect':
        with worker_lock(directory): assert retry_archive(store,config,ids[0])['state']=='uncertain'
        assert len(session.copies)==1
        session.matches=[store.get_message(ids[0])['message_id']]
        with worker_lock(directory): assert retry_archive(store,config,ids[0])['state']=='archived'
        assert len(session.copies)==1
    assert Worker(store,smtp,config,Clock()).run('archive','fictional-batch',1,max_attempts=1)==result or mode in ('reject','disconnect')
    assert smtp.sent==[ids[0]]
    store.close()


def test_transmitted_bytes_including_dkim_preserved(account,batch_file,monkeypatch):
    directory,config=account
    store=Store(directory); identity=import_batch(store,config,batch_file)['ids'][0]
    sent=[]
    class SMTP:
        sock=None
        def ehlo(self): return 250,b'ok'
        def login(self,*args): pass
        def mail(self,*args): return 250,b'ok'
        def rcpt(self,*args): return 250,b'ok'
        def data(self,wire): sent.append(wire); return 250,b'ok'
        def quit(self): pass
        def close(self): pass
    import dkim
    from mailqueue.dkim_signing import generate_key
    private,record=generate_key()
    config['dkim']=dict(domain='example.com', selector='simulated', record=record, enabled=True)
    class Backend:
        def get_password(self,*args): return private
    monkeypatch.setattr('mailqueue.credentials.native_backend',lambda:Backend())
    session=Session(); installed_session(monkeypatch,session)
    Worker(store,SMTPTransport(config,lambda *a,**k:SMTP()),config,Clock()).run('wire','fictional-batch',1,max_attempts=1)
    assert session.copies==sent
    assert session.copies[0].endswith(store.get_message(identity)['mime_bytes'])
    assert dkim.verify(session.copies[0],dnsfunc=lambda *a,**k:record.encode())
    store.close()


@pytest.mark.parametrize('mode', ['5xx','disconnect'])
def test_no_archive_for_smtp_failure(account,batch_file,monkeypatch,mode):
    from test_smtp import Session as SMTP
    directory,config=account; store=Store(directory)
    ids=import_batch(store,config,batch_file)['ids']
    session=Session(); installed_session(monkeypatch,session)
    smtp=SMTP(mode); smtp.actions.append('tls')
    Worker(store,SMTPTransport(config,lambda *a,**k:smtp),config,Clock()).run('bad','fictional-batch',1,max_attempts=1)
    assert store.db.execute('SELECT count(*) FROM archives').fetchone()[0]==0
    assert session.actions==[]
    store.close()


def pending_archive(directory, config, batch_file):
    store=Store(directory)
    ids=import_batch(store,config,batch_file)['ids']
    # Commit sent with request without invoking IMAP yet.
    from mailqueue.worker import create_run
    run,_=create_run(store,'pending','fictional-batch',1,now=1700000000)
    worker=Worker(store,Simulated(),config,Clock())
    message,attempt=worker.reserve(run)
    worker.accept(message['id'],attempt,message)
    return store,message['id']


def test_exact_message_id_and_duplicates(account,batch_file,monkeypatch):
    directory,config=account; store,identity=pending_archive(directory,config,batch_file)
    session=Session(); installed_session(monkeypatch,session)
    mid=store.get_message(identity)['message_id']
    session.matches=[mid+'suffix']
    assert retry_archive(store,config,identity)['state']=='archived'
    assert len(session.copies)==1  # substring does not count as an existing copy
    store.db.execute("UPDATE archives SET state='uncertain' WHERE message_id=?",(identity,))
    session.matches=[mid,mid]
    assert retry_archive(store,config,identity)['last_error_code']=='IMAP_DUPLICATES_FOUND'
    assert len(session.copies)==1
    store.close()


def test_folder_frozen_and_account_isolation(account,batch_file,monkeypatch):
    directory,config=account; store,identity=pending_archive(directory,config,batch_file)
    session=Session(); installed_session(monkeypatch,session)
    with pytest.raises(QueueError,match='conta ativa'):
        retry_archive(store,dict(config,account_id='other'),identity)
    changed=dict(config,archive=dict(folder='other'))
    assert retry_archive(store,changed,identity)['state']=='archived'
    assert ('select','"INBOX.Outgoing Mail"') in session.actions
    count=len(session.actions)
    assert retry_archive(store,changed,identity)['state']=='archived'
    assert len(session.actions)==count
    store.close()


def test_migration_no_history_backfill(account,batch_file):
    directory,config=account; store=Store(directory)
    import_batch(store,config,batch_file)
    before=[tuple(row) for row in store.db.execute('SELECT * FROM messages ORDER BY id')]
    store.db.execute('DROP TABLE archives'); store.db.execute('DELETE FROM schema_migrations WHERE version=6')
    store.close(); store=Store(directory)
    assert [tuple(row) for row in store.db.execute('SELECT * FROM messages ORDER BY id')]==before
    assert store.db.execute('SELECT count(*) FROM archives').fetchone()[0]==0
    identity=store.db.execute('SELECT id FROM messages LIMIT 1').fetchone()[0]
    assert archive_status(store,identity)==dict(state='not_requested')
    with pytest.raises(QueueError) as exc: retry_archive(store,config,identity)
    assert exc.value.code=='ARCHIVE_NOT_REQUESTED'
    store.close()


@pytest.mark.parametrize('special', [True,False])
def test_configure_discovery_no_append(account,monkeypatch,special):
    directory,config=account; config.pop('archive'); (directory/'config.json').write_text(json.dumps(config))
    session=Session(folders=None if special else [b'(\\HasNoChildren) "." INBOX'])
    factory=installed_session(monkeypatch,session)
    result=configure(directory,'configure',factory=factory)
    assert result['enabled']==special
    assert result['appended'] is False
    assert not session.copies
    if special:
        assert load_config(directory)['archive']['folder']=='INBOX.Outgoing Mail'
    else:
        assert result['needs_folder']
        assert 'archive' not in load_config(directory)
    assert not any(isinstance(a,tuple) and a[0]=='create' for a in session.actions)


def test_explicit_creation_check_disable(account,monkeypatch):
    directory,config=account; session=Session(folders=[b'(\\HasNoChildren) "." INBOX'])
    factory=installed_session(monkeypatch,session)
    with pytest.raises(QueueError): configure(directory,'configure','INBOX.New',factory=factory)
    result=configure(directory,'configure','INBOX.New',True,factory)
    assert result['enabled'] and result['folder']=='INBOX.New'
    assert ('subscribe','"INBOX.New"') in session.actions
    assert configure(directory,'check',factory=factory)['appended'] is False
    assert configure(directory,'disable')['enabled'] is False
    assert not session.copies


def test_tls_before_keychain(account,monkeypatch):
    directory,config=account
    def no_secret(*args): pytest.fail('TLS inválido deve bloquear credencial')
    monkeypatch.setattr('mailqueue.credentials.retrieve',no_secret)
    def bad(*args,**kwargs): raise ssl.SSLCertVerificationError('private')
    with pytest.raises(QueueError) as exc: configure(directory,'check',factory=bad)
    assert exc.value.code=='IMAP_TLS_INVALID'


def test_cli_status_and_retry_error(account,batch_file,monkeypatch,capsys):
    directory,config=account; store,identity=pending_archive(directory,config,batch_file); store.close()
    session=Session('reject'); installed_session(monkeypatch,session)
    assert main(['--data-dir',str(directory),'archive','retry',identity,'--json'])==5
    data=json.loads(capsys.readouterr().out)
    assert data['error']['code']=='ARCHIVE_ATTENTION'
    assert data['error']['details']['state']=='failed'
    assert main(['--data-dir',str(directory),'show',identity,'--json'])==0
    data=json.loads(capsys.readouterr().out)['data']
    assert data['archive']['state']=='failed' and data['state']=='sent'
    assert 'wire_bytes' not in data['archive']


@pytest.mark.parametrize('stage', ['before_append','after_reservation','after_append','before_commit'])
def test_process_crash_reconciles_no_duplicates(account,batch_file,monkeypatch,stage):
    directory,config=account; store,identity=pending_archive(directory,config,batch_file)
    store.close()
    remote=directory/'remote.eml'
    result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('imap_crash_driver.py')),str(directory),identity,stage],capture_output=True,text=True)
    assert result.returncode==77, result.stderr
    store=Store(directory)
    session=Session(); installed_session(monkeypatch,session)
    if remote.exists(): session.matches=[store.get_message(identity)['message_id']]
    before=archive_status(store,identity)['state']
    result=retry_archive(store,config,identity)
    if stage=='before_append':
        assert before=='pending' and result['state']=='archived' and len(session.copies)==1
    elif stage=='after_reservation':
        assert before=='appending' and result['state']=='uncertain' and session.copies==[]
    else:
        assert before=='appending' and result['state']=='archived' and session.copies==[]
        assert remote.read_bytes()==store.get_message(identity)['mime_bytes']
    assert store.get_message(identity)['state']=='sent'
    assert store.db.execute('SELECT count(*) FROM attempts').fetchone()[0]==1
    store.close()


def test_atomic_sent_archive_and_backup_block(account,batch_file):
    directory,config=account; store,identity=pending_archive(directory,config,batch_file)
    store.backup(directory/'backup.db')
    target=directory/'restored'; target.mkdir(); (directory/'backup.db').rename(target/'queue.db')
    backup=Store(target)
    with pytest.raises(QueueError) as exc: retry_archive(backup,config,identity)
    assert exc.value.code=='BACKUP_RECONCILIATION_REQUIRED'
    backup.close(); store.close()


def test_sent_commit_rolls_back_if_request_cannot_persist(account,batch_file,monkeypatch):
    directory,config=account; store=Store(directory)
    ids=import_batch(store,config,batch_file)['ids']
    store.db.execute("CREATE TRIGGER deny_archive BEFORE INSERT ON archives BEGIN SELECT RAISE(ABORT,'failure'); END")
    smtp=Simulated()
    with pytest.raises(sqlite3.IntegrityError):
        Worker(store,smtp,config,Clock()).run('rollback','fictional-batch',1,max_attempts=1)
    assert smtp.sent==[ids[0]]
    assert store.get_message(ids[0])['state']=='sending'
    worker=Worker(store,smtp,config,Clock())
    with worker_lock(directory): worker.recover()
    assert store.get_message(ids[0])['state']=='uncertain'
    assert store.db.execute('SELECT count(*) FROM archives').fetchone()[0]==0
    assert smtp.sent==[ids[0]]
    store.close()
