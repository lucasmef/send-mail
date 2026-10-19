import contextlib
import fcntl
import os
import random
import signal
import threading
import time
import uuid
from .composer import digest
from .errors import QueueError
from .transport import DeliveryError


@contextlib.contextmanager
def worker_lock(directory):
    fd = os.open(directory / "worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise QueueError("WORKER_BUSY", "Outro worker está ativo neste diretório.", 6, True)
        yield
    finally:
        os.close(fd)


def get_run(store, identity):
    row = store.db.execute("SELECT * FROM runs WHERE id=?", (identity,)).fetchone()
    if row is None:
        raise QueueError("NOT_FOUND", "Execução não encontrada.")
    return row


def status(store, identity):
    run = dict(get_run(store,identity))
    counts = {state:0 for state in ("pending","sending","retry_wait","sent","failed","uncertain","cancelled")}
    for row in store.db.execute("SELECT m.state,count(*) AS n FROM messages m WHERE m.run_id=? GROUP BY m.state", (identity,)):
        counts[row["state"]] = row["n"]
    historical = dict(store.db.execute("SELECT count(*) AS attempts,count(DISTINCT message_id) AS messages FROM attempts WHERE run_id=?", (identity,)).fetchone())
    outcomes = {row["outcome"]:row["n"] for row in store.db.execute("SELECT outcome,count(*) AS n FROM attempts WHERE run_id=? AND outcome IS NOT NULL GROUP BY outcome", (identity,))}
    archives = {row['state']: row['n'] for row in store.db.execute(
        'SELECT a.state,count(*) AS n FROM archives a JOIN messages m ON m.id=a.message_id WHERE m.run_id=? GROUP BY a.state', (identity,))}
    return dict(archives=archives, run_id=run.pop("id"), **run, counts=counts, history=historical, outcomes=outcomes)


def existing_run(store, request, params):
    row = store.db.execute("SELECT * FROM runs WHERE request_id=?", (request,)).fetchone()
    if row is not None and row["params_hash"] != digest(params):
        raise QueueError("IDEMPOTENCY_CONFLICT", "Chave de execução usada com outros parâmetros.", 3)
    return row


def create_run(store, request, batch, limit, max_attempts=100, max_seconds=3600, now=None):
    if request.startswith("__test__:"):
        raise QueueError("INVALID_REQUEST_ID","Prefixo reservado para cópias de teste.")
    if not request or not batch or limit<=0 or max_attempts<=0 or max_seconds<=0:
        raise QueueError("INVALID_LIMIT", "Informe chave, lote e limites positivos.")
    params = [batch,limit,max_attempts,max_seconds]
    with store.transaction():
        existing = existing_run(store,request,params)
        if existing:
            return existing["id"], False
        identity, now = "r_" + uuid.uuid4().hex, time.time() if now is None else now
        store.db.execute("INSERT INTO runs(id,request_id,params_hash,batch_id,state,max_messages,max_attempts,max_active_seconds,created_at,updated_at) VALUES(?,?,?,?,'running',?,?,?,?,?)", (identity,request,digest(params),batch,limit,max_attempts,max_seconds,now,now))
    return identity, True


class Worker:
    def __init__(self, store, transport, config, clock=time):
        self.store, self.transport, self.config, self.clock = store, transport, config, clock
        self.interval_min = float(config.get("interval_min_seconds", config.get("interval_seconds", 15)))
        self.interval_max = float(config.get("interval_max_seconds", max(45, self.interval_min + 30)))

    def checkpoint(self, identity):
        now = self.clock.monotonic()
        elapsed = max(0,now-self.last_checkpoint)
        self.last_checkpoint=now
        with self.store.transaction():
            self.store.db.execute("UPDATE runs SET active_seconds=active_seconds+?,heartbeat_at=?,updated_at=? WHERE id=?",(elapsed,self.clock.time(),self.clock.time(),identity))
            if self.stop_requested:
                self.store.db.execute("UPDATE runs SET pause_requested=1 WHERE id=?",(identity,))

    def wait(self, identity, seconds):
        end = self.clock.monotonic()+seconds
        while self.clock.monotonic()<end:
            self.checkpoint(identity)
            run=get_run(self.store,identity)
            if run['pause_requested'] or run['active_seconds']>=run['max_active_seconds']:
                return
            self.clock.sleep(min(1,end-self.clock.monotonic(),run['max_active_seconds']-run['active_seconds']))
        self.checkpoint(identity)

    def set_run(self, identity, state, reason=None):
        now = self.clock.time()
        with self.store.transaction():
            resume_after=None
            if reason=='SMTP_THROTTLED': resume_after=now+3600
            self.store.db.execute("UPDATE runs SET state=?,blocked_reason=?,updated_at=?,finished_at=?,resume_after=? WHERE id=?", (state,reason,now,now if state in ('completed','limit_reached') else None,resume_after,identity))

    def reserve(self, identity):
        store, now = self.store, self.clock.time()
        with store.transaction():
            run = get_run(store,identity)
            if run["pause_requested"]:
                store.db.execute("UPDATE runs SET state='paused',updated_at=? WHERE id=?",(now,identity)); return None
            if run["attempts_started"] >= run["max_attempts"] or run["active_seconds"] >= run["max_active_seconds"]:
                store.db.execute("UPDATE runs SET state='limit_reached',finished_at=?,updated_at=? WHERE id=?",(now,now,identity)); return None
            row = store.db.execute("""SELECT m.* FROM messages m LEFT JOIN runs owner ON owner.id=m.run_id
                 WHERE m.account_id=? AND m.batch_id=? AND (m.kind='normal' OR m.id=?) AND (? IS NULL OR m.id=?) AND m.attempt_count<5
                 AND (m.state='pending' OR (m.state='retry_wait' AND m.next_attempt_at<=?))
                 AND (m.run_id IS NULL OR m.run_id=? OR owner.state IN('completed','limit_reached'))
                 ORDER BY CASE WHEN EXISTS(SELECT 1 FROM attempts a WHERE a.message_id=m.id AND a.run_id=?) THEN 0 ELSE 1 END,m.created_at,m.id LIMIT 1""",(self.config["account_id"],run["batch_id"],run["test_message_id"],run["test_message_id"],run["test_message_id"],now,identity,identity)).fetchone()
            if row is None:
                return None
            previous = store.db.execute("SELECT 1 FROM attempts WHERE run_id=? AND message_id=?",(identity,row["id"])).fetchone()
            if not previous and run["messages_started"] >= run["max_messages"]:
                return None
            attempt = "a_" + uuid.uuid4().hex
            store.db.execute("INSERT INTO attempts(id,message_id,run_id,started_at,phase,delay_seconds) VALUES(?,?,?,?,'reserved',?)", (attempt,row["id"],identity,now,random.uniform(self.interval_min, self.interval_max)))
            store.db.execute("UPDATE messages SET state='sending',run_id=?,attempt_count=attempt_count+1,updated_at=? WHERE id=?",(identity,now,row["id"]))
            store.db.execute("UPDATE runs SET attempts_started=attempts_started+1,messages_started=messages_started+?,heartbeat_at=?,updated_at=? WHERE id=?",(0 if previous else 1,now,now,identity))
        return dict(row), attempt

    def event(self, attempt, phase):
        with self.store.transaction():
            if phase=='submission_started':
                now=self.clock.time()
                self.store.db.execute("UPDATE attempts SET phase=?,submission_reserved_at=? WHERE id=?",(phase,now,attempt))
            else:
                self.store.db.execute("UPDATE attempts SET phase=? WHERE id=?",(phase,attempt))

    def accept(self, identity, attempt, message=None):
        now = self.clock.time()
        with self.store.transaction():
            self.store.db.execute("UPDATE messages SET state='sent',sent_at=?,updated_at=?,confirmation_source='smtp',last_error_code=NULL,next_attempt_at=NULL WHERE id=?",(now,now,identity))
            self.store.db.execute("UPDATE attempts SET phase='accepted',outcome='success',smtp_code=250,finished_at=? WHERE id=?",(now,attempt))

            if message is not None:
                from .archiving import record_accepted
                record_accepted(self.store, message, self.config, now)

    def fail(self, message, attempt, error):
        now = self.clock.time()
        state = {'transient':'retry_wait','permanent':'failed','uncertain':'uncertain'}[error.outcome]
        if state == 'retry_wait' and message['attempt_count']+1>=5:
            state='failed'
        with self.store.transaction():
            self.store.db.execute("UPDATE messages SET state=?,last_error_code=?,updated_at=?,next_attempt_at=? WHERE id=?",(state,error.code,now,now + (60,300,900,3600)[min(message['attempt_count'],3)] + random.uniform(0,5) if state=='retry_wait' else None,message['id']))
            self.store.db.execute("UPDATE attempts SET outcome=?,error_code=?,smtp_code=?,finished_at=? WHERE id=?",(error.outcome,error.code,error.smtp_code,now,attempt))
            if error.block:
                resume_after=None
                if error.code=='SMTP_THROTTLED': resume_after=now+3600
                self.store.db.execute("UPDATE runs SET state='blocked',blocked_reason=?,resume_after=?,updated_at=? WHERE id=?",(error.code,resume_after,now,self.store.db.execute('SELECT run_id FROM attempts WHERE id=?',(attempt,)).fetchone()[0]))

    def future_wait(self, identity):
        run=get_run(self.store,identity)
        rows=list(self.store.db.execute("""SELECT m.* FROM messages m LEFT JOIN runs owner ON owner.id=m.run_id
          WHERE m.account_id=? AND m.batch_id=? AND (m.kind='normal' OR m.id=?) AND (? IS NULL OR m.id=?) AND m.attempt_count<5 AND m.state IN('pending','retry_wait')
          AND (m.run_id IS NULL OR m.run_id=? OR owner.state IN('completed','limit_reached'))""",(self.config['account_id'],run['batch_id'],run['test_message_id'],run['test_message_id'],run['test_message_id'],identity)))
        if not rows:
            return None
        eligible=[]
        for row in rows:
            started=self.store.db.execute("SELECT 1 FROM attempts WHERE run_id=? AND message_id=?",(identity,row['id'])).fetchone()
            if started or run['messages_started']<run['max_messages']:
                eligible.append(row)
        if not eligible:
            self.set_run(identity,'limit_reached'); return None
        return max(0,min(row['next_attempt_at'] or self.clock.time() for row in eligible)-self.clock.time())

    def process(self, identity):
        self.last_checkpoint=self.clock.monotonic()
        self.stop_requested=False
        previous_handler=None
        if threading.current_thread() is threading.main_thread():
            previous_handler=signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT,lambda *_:setattr(self,'stop_requested',True))
        try:
            while True:
                self.checkpoint(identity)
                run=get_run(self.store,identity)
                if run['pause_requested']:
                    self.set_run(identity,'paused'); break
                if run['attempts_started']>=run['max_attempts'] or run['active_seconds']>=run['max_active_seconds']:
                    self.set_run(identity,'limit_reached'); break
                cooldown=self.store.db.execute("SELECT max(resume_after) FROM runs WHERE resume_after>?",(self.clock.time(),)).fetchone()[0]
                if cooldown is not None:
                    self.set_run(identity,'blocked','ACCOUNT_COOLDOWN')
                    with self.store.transaction():
                        self.store.db.execute('UPDATE runs SET resume_after=? WHERE id=?',(cooldown,identity))
                    break
                latest=self.store.db.execute("SELECT max(coalesce(finished_at,started_at)+delay_seconds) FROM attempts").fetchone()[0]
                if latest is not None:
                    remaining=latest-self.clock.time()
                    if remaining>0:
                        self.wait(identity,remaining)
                reserved=self.reserve(identity)
                if reserved is None:
                    run=get_run(self.store,identity)
                    if run['state']!='running':
                        break
                    delay=self.future_wait(identity)
                    if delay is not None:
                        self.wait(identity,max(0.01,delay)); continue
                    if get_run(self.store,identity)['state']=='running':
                        self.set_run(identity,'completed')
                    break
                message,attempt=reserved
                try:
                    self.transport.send(message,lambda phase:self.event(attempt,phase))
                except DeliveryError as error:
                    self.fail(message,attempt,error)
                    if error.block:
                        break
                else:
                    self.accept(message['id'],attempt,message)
                finally:
                    with contextlib.suppress(Exception):
                        self.transport.close()
                if self.config.get('archive') and self.store.get_message(message['id'])['state'] == 'sent':
                    from .archiving import retry_archive
                    retry_archive(self.store, self.config, message['id'])
                self.checkpoint(identity)
            self.checkpoint(identity)
            return status(self.store,identity)
        finally:
            if previous_handler is not None:
                signal.signal(signal.SIGINT,previous_handler)

    def recover(self):
        # Somente chamar mantendo o lock OS; heartbeat não prova abandono.
        now=self.clock.time()
        with self.store.transaction():
            rows=list(self.store.db.execute("SELECT m.id,m.attempt_count,a.id AS attempt_id,a.phase,a.submission_reserved_at FROM messages m JOIN attempts a ON a.message_id=m.id WHERE m.state='sending' AND a.finished_at IS NULL"))
            for row in rows:
                uncertain=row['submission_reserved_at'] is not None or row['phase'] in ('submission_started','accepted')
                state='uncertain' if uncertain else ('failed' if row['attempt_count']>=5 else 'retry_wait')
                error='RECOVERED_UNCERTAIN' if uncertain else 'RECOVERED_SAFE'
                delay=(60,300,900,3600)[min(max(row['attempt_count']-1,0),3)]
                self.store.db.execute("UPDATE messages SET state=?,last_error_code=?,next_attempt_at=?,updated_at=? WHERE id=?",(state,error,None if uncertain or state=='failed' else now+delay,now,row['id']))
                self.store.db.execute("UPDATE attempts SET outcome=?,error_code=?,finished_at=? WHERE id=?",('uncertain' if uncertain else 'transient',error,now,row['attempt_id']))
            self.store.db.execute("UPDATE runs SET state='interrupted',updated_at=? WHERE state='running'",(now,))

    def resume(self, identity):
        with worker_lock(self.store.path.parent):
            self.store.ensure_sendable()
            self.recover()
            run=get_run(self.store,identity)
            if run['state'] in ('completed','limit_reached'):
                return status(self.store,identity)
            if run['resume_after'] is not None and run['resume_after']>self.clock.time():
                return status(self.store,identity)
            if run['state']=='running':
                raise QueueError('INVALID_STATE','Execução ativa ou interrompida sem recuperação.',3)
            with self.store.transaction():
                self.store.db.execute("UPDATE runs SET state='running',pause_requested=0,blocked_reason=NULL,updated_at=? WHERE id=?",(self.clock.time(),identity))
            return self.process(identity)

    def run(self, request, batch, limit, max_attempts=100, max_seconds=3600):
        params = [batch,limit,max_attempts,max_seconds]
        existing=existing_run(self.store,request,params)
        if existing:
            return status(self.store,existing['id'])
        with worker_lock(self.store.path.parent):
            self.store.ensure_sendable()
            self.recover()
            identity, created = create_run(self.store,request,batch,limit,max_attempts,max_seconds,self.clock.time())
            return self.process(identity) if created else status(self.store,identity)


def pause(store, identity):
    with store.transaction():
        run=get_run(store,identity)
        if run['state'] in ('completed','limit_reached'):
            raise QueueError('INVALID_STATE','Execução já encerrada.',3)
        store.db.execute("UPDATE runs SET pause_requested=1,updated_at=? WHERE id=?",(time.time(),identity))
    return status(store,identity)
