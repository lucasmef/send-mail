import sqlite3
import threading
import pytest
from mailqueue.storage import Store
from mailqueue.errors import QueueError


def test_migration_rollback_reopen(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction():
            store.db.execute("INSERT INTO schema_migrations VALUES(99,0,0)")
            store.db.execute("INSERT INTO schema_migrations VALUES(99,0,0)")
    assert store.db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 6
    store.close()
    store = Store(tmp_path)
    assert store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert store.db.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert tmp_path.stat().st_mode & 0o777 == 0o700
    assert store.path.stat().st_mode & 0o777 == 0o600
    store.close()


def test_backup_while_writing(tmp_path):
    directory = tmp_path / "data"
    main = Store(directory)
    done = threading.Event()
    def write():
        other = Store(directory)
        for i in range(30):
            with other.transaction():
                other.db.execute("UPDATE schema_migrations SET applied_at=?", (i,))
        other.close()
        done.set()
    thread = threading.Thread(target=write)
    thread.start()
    output = tmp_path / "copy.db"
    main.backup(output)
    thread.join()
    assert done.is_set()
    copy = sqlite3.connect(output)
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert copy.execute("SELECT sending_blocked FROM schema_migrations").fetchone()[0] == 1
    copy.close()
    main.ensure_sendable()
    with pytest.raises(FileExistsError):
        main.backup(output)
    main.close()


def test_upgrade_preserves_message(tmp_path):
    from pathlib import Path
    import mailqueue.storage
    from mailqueue.composer import compose
    content=compose(dict(external_id='old',to='person@example.com',subject='Antiga',html='<p>Congelada</p>'),{'sender':'sender@example.com'},('',''))
    db=sqlite3.connect(tmp_path/'queue.db')
    migration=Path(mailqueue.storage.__file__).parent/'migrations/001_initial.sql'
    db.executescript(migration.read_text())
    db.execute('INSERT INTO schema_migrations(version,applied_at) VALUES(1,0)')
    values=dict(id='m_old',batch_id='old',external_id='old',account_id='fictional',created_at=0,updated_at=0,state='sent',confirmation_source='manual',resolution_action='mark-sent',resolution_reason='Recebimento confirmado',resolved_at=0,**content)
    db.execute('INSERT INTO messages ('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))
    db.commit(); db.close()
    store=Store(tmp_path)
    row=store.get_message('m_old')
    assert row['mime_bytes']==content['mime_bytes'] and row['state']=='sent'
    assert 'Recebimento confirmado' in row['resolution_history_json']
    assert store.db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0]==6
    store.close()


def test_remove_only_legacy_daily_cooldowns(tmp_path):
    from pathlib import Path
    import mailqueue.storage
    db=sqlite3.connect(tmp_path/'queue.db')
    root=Path(mailqueue.storage.__file__).parent/'migrations'
    for path in sorted(root.glob('*.sql'))[:4]:
        db.executescript(path.read_text())
        db.execute('INSERT INTO schema_migrations(version,applied_at) VALUES(?,0)',(int(path.name.split('_')[0]),))
    cases=[('local','DAILY_BUDGET',100),('local-copy','ACCOUNT_COOLDOWN',100),('provider','SMTP_THROTTLED',200),('provider-copy','ACCOUNT_COOLDOWN',200)]
    for identity,reason,until in cases:
        db.execute("INSERT INTO runs(id,request_id,params_hash,batch_id,state,max_messages,max_attempts,max_active_seconds,created_at,updated_at,blocked_reason,resume_after) VALUES(?,?,?,'test','blocked',1,1,100,0,0,?,?)",(identity,identity,identity,reason,until))
    db.commit(); db.close()
    store=Store(tmp_path)
    result=dict(store.db.execute('SELECT id,resume_after FROM runs'))
    assert result=={'local':None,'local-copy':None,'provider':200,'provider-copy':200}
    store.close()
