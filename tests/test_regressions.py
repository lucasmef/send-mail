import json
from pathlib import Path
import pytest
from mailqueue import cli
from mailqueue.config import data_path
from mailqueue.errors import QueueError
from mailqueue.importer import import_batch
from mailqueue.storage import Store
from mailqueue.worker import Worker
from mailqueue.transport import DeliveryError
from mailqueue.resolution import resolve
from test_worker import Simulated
from fakes import Clock


def test_retry_same_message_after_distinct_limit(configured,batch_file):
    directory,config=configured; store=Store(directory)
    import_batch(store,config,batch_file)
    class RetryOnce(Simulated):
        first=True
        def send(self,message,event):
            if self.first:
                self.first=False; event('submission_started'); raise DeliveryError('SMTP_451',smtp_code=451)
            assert not store.db.in_transaction
            super().send(message,event)
    result=Worker(store,RetryOnce(),config,Clock()).run('limit-retry','fictional-batch',1)
    assert result['attempts_started']==2
    assert result['messages_started']==1
    assert result['state']=='limit_reached'
    assert store.db.execute('SELECT count(*) FROM attempts WHERE submission_reserved_at IS NOT NULL').fetchone()[0]==2
    assert store.db.execute("SELECT count(*) FROM messages WHERE state='pending'").fetchone()[0]==2
    store.close()


def test_account_cooldown_new_run_and_expiry(configured,batch_file):
    directory,config=configured; store=Store(directory)
    import_batch(store,config,batch_file)
    clock=Clock()
    class Throttled(Simulated):
        def send(self,message,event):
            raise DeliveryError('SMTP_THROTTLED',block=True)
    result=Worker(store,Throttled(),config,clock).run('quota','fictional-batch',3)
    assert result['state']=='blocked'
    second=Worker(store,Simulated(),config,clock).run('new-quota','fictional-batch',3)
    assert second['state']=='blocked' and second['attempts_started']==0
    clock.sleep(86400+30)
    resumed=Worker(store,Simulated(),config,clock).resume(result['run_id'])
    assert resumed['counts']['sent']==3
    assert resumed['attempts_started']==4
    store.close()


def test_manual_history_preserved(configured,batch_file):
    directory,config=configured; store=Store(directory)
    identity=import_batch(store,config,batch_file)['ids'][0]
    store.db.execute("UPDATE messages SET state='uncertain' WHERE id=?",(identity,))
    first=resolve(store,identity,'resend','Primeira decisão','history-copy')
    last=resolve(store,identity,'mark-sent','Confirmação posterior')
    assert [entry['reason'] for entry in last['resolution_history']]==['Primeira decisão','Confirmação posterior']
    assert first['state']=='pending'
    store.close()


def test_backup_refused_by_worker(configured,batch_file,tmp_path):
    directory,config=configured; store=Store(directory)
    import_batch(store,config,batch_file)
    copied=tmp_path/'restored'; copied.mkdir()
    store.backup(copied/'queue.db'); store.close()
    restored=Store(copied)
    with pytest.raises(QueueError) as error: Worker(restored,Simulated(),config,Clock()).run('restore','fictional-batch',3)
    assert error.value.code=='BACKUP_RECONCILIATION_REQUIRED'
    assert restored.db.execute('SELECT count(*) FROM attempts').fetchone()[0]==0
    restored.close()


def test_bad_config_and_data_path(configured,capsys):
    directory,config=configured
    (directory/'config.json').write_text(json.dumps({**config,'sender':'bad\nheader'}))
    assert cli.main(['--data-dir',str(directory),'doctor'])==4
    assert json.loads(capsys.readouterr().out)['error']['code']=='CONFIG_INVALID'
    with pytest.raises(QueueError): data_path(Path.cwd()/'operational')
    with pytest.raises(QueueError): data_path('/tmp/Dropbox-account/operational')


def test_setup_cli_json_contract(tmp_path,monkeypatch,capsys):
    from mailqueue import credentials
    (tmp_path/'sig.html').write_text('<p>Assinatura fictícia</p>'); (tmp_path/'sig.txt').write_text('Assinatura fictícia')
    values=iter(['fictional@icloud.com','sender@example.com',str(tmp_path/'sig.html'),str(tmp_path/'sig.txt')])
    monkeypatch.setattr('builtins.input',lambda:next(values))
    import uuid
    opaque=uuid.uuid4().hex
    monkeypatch.setattr(credentials,'secure_password',lambda *args:opaque)
    monkeypatch.setattr(credentials,'save',lambda *args:None)
    assert cli.main(['--data-dir',str(tmp_path/'data'),'setup'])==0
    captured=capsys.readouterr()
    assert json.loads(captured.out)['ok'] is True
    assert opaque not in captured.out+captured.err
