import contextlib
import os
from pathlib import Path
import sqlite3
import time
from .config import prepare_dir, data_path
from .errors import QueueError


class Store:
    def __init__(self, directory):
        prepare_dir(directory)
        self.path = directory / "queue.db"
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.path.chmod(0o600)
        # journal_mode pode responder busy antes de instalar o timeout em um banco novo.
        deadline=time.monotonic()+5
        while True:
            try:
                self.db.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError as exc:
                if 'locked' not in str(exc).lower() or time.monotonic()>=deadline:
                    self.db.close()
                    raise QueueError('DATABASE_BUSY','Banco ocupado; tente novamente.',3,True)
                time.sleep(0.02)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.migrate()
        for suffix in ("-wal", "-shm"):
            extra = Path(str(self.path) + suffix)
            if extra.exists():
                extra.chmod(0o600)

    def migrate(self):
        with self.transaction():
            exists = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
            current = self.db.execute("SELECT coalesce(max(version),0) FROM schema_migrations").fetchone()[0] if exists else 0
            migrations = sorted((Path(__file__).parent / "migrations").glob("*.sql"))
            if current > len(migrations):
                raise QueueError("SCHEMA_NEWER", "Banco criado por versão mais recente.", 4)
            for file in migrations:
                version = int(file.name.split("_")[0])
                if version > current:
                    # execute() mantém a transação; executescript() faria commit implícito.
                    for statement in file.read_text().split(";"):
                        if statement.strip():
                            self.db.execute(statement)
                    self.db.execute("INSERT INTO schema_migrations(version,applied_at) VALUES (?,?)", (version,time.time()))

    @contextlib.contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()

    def get_message(self, identity):
        row = self.db.execute("SELECT * FROM messages WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise QueueError("NOT_FOUND", "Mensagem não encontrada.")
        return row

    def backup(self, output):
        output = Path(output).expanduser().resolve()
        data_path(output.parent)
        if output == self.path.resolve():
            raise QueueError("INVALID_OUTPUT", "O backup precisa de outro arquivo.")
        # Não sobrescrever arquivo existente nem seguir symlink.
        fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        target = sqlite3.connect(output)
        try:
            self.db.backup(target)
            target.execute("UPDATE schema_migrations SET sending_blocked=1")
            target.commit()
            assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            target.close()
        return {"path": str(output), "sending_blocked": True}

    def ensure_sendable(self):
        if self.db.execute("SELECT max(sending_blocked) FROM schema_migrations").fetchone()[0]:
            raise QueueError("BACKUP_RECONCILIATION_REQUIRED", "Backup bloqueado para envio; reconciliação necessária.", 4)
