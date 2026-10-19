import base64
import json
import os
import time
from pathlib import Path
from .errors import QueueError
from .config import data_path

STATES = ("pending", "sending", "retry_wait", "sent", "failed", "uncertain", "cancelled")
PUBLIC = ("id","batch_id","external_id","account_id","sender","recipient","subject","message_id","kind","source_message_id","request_id","state","run_id","attempt_count","next_attempt_at","last_error_code","created_at","updated_at","sent_at","confirmation_source","resolution_action","resolution_reason","resolved_at")


def metadata(row, include_body=False):
    result = {key:row[key] for key in PUBLIC}
    result["resolution_history"]=json.loads(row["resolution_history_json"])
    if include_body:
        result.update(html=row["html"], text=row["text"], mime_base64=base64.b64encode(row["mime_bytes"]).decode("ascii"))
    return result


def show(store, identity, include_body=False):
    result = metadata(store.get_message(identity), include_body)
    from .archiving import archive_status
    result["archive"] = archive_status(store, identity)
    result["attempts"] = [dict(row) for row in store.db.execute("SELECT * FROM attempts WHERE message_id=? ORDER BY started_at,id", (identity,))]
    return result


def list_messages(store, batch=None, state=None, limit=20, cursor=None):
    if not 1 <= limit <= 100:
        raise QueueError("INVALID_LIMIT", "Limite da página deve estar entre 1 e 100.")
    filters, values = [], []
    if batch:
        filters.append("batch_id=?"); values.append(batch)
    if state:
        if state not in STATES:
            raise QueueError("INVALID_STATE", "Estado desconhecido.")
        filters.append("state=?"); values.append(state)
    predicate = " AND ".join(filters) or "1"
    counts = {s:0 for s in STATES}
    for row in store.db.execute("SELECT state,count(*) AS n FROM messages WHERE " + predicate + " GROUP BY state", values):
        counts[row["state"]] = row["n"]
    if cursor:
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if token["batch"] != batch or token["state"] != state:
                raise ValueError()
            filters.append("(created_at,id)>(?,?)"); values.extend([token["at"], token["id"]])
        except (ValueError, KeyError, TypeError):
            raise QueueError("INVALID_CURSOR", "Cursor inválido para estes filtros.")
    rows = list(store.db.execute("SELECT * FROM messages WHERE " + (" AND ".join(filters) or "1") + " ORDER BY created_at,id LIMIT ?", (*values,limit+1)))
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps(dict(batch=batch,state=state,at=last["created_at"],id=last["id"])).encode()).decode()
    return dict(messages=[metadata(row) for row in page], counts=counts, next_cursor=next_cursor)


def cancel(store, identity):
    with store.transaction():
        row = store.get_message(identity)
        submitted = store.db.execute("SELECT 1 FROM attempts WHERE message_id=? AND submission_reserved_at IS NOT NULL", (identity,)).fetchone()
        if row["state"] not in ("pending", "retry_wait") or submitted:
            raise QueueError("INVALID_STATE", "Cancelamento exige item não submetido e sem tentativa em andamento.", 3)
        store.db.execute("UPDATE messages SET state='cancelled',updated_at=? WHERE id=?", (time.time(),identity))
    return show(store, identity)


def write_private(path, content):
    path = Path(path).expanduser().resolve()
    data_path(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return str(path)


def export_batch(store, batch, output):
    with store.transaction():
        rows = list(store.db.execute("SELECT id FROM messages WHERE batch_id=? ORDER BY created_at,id", (batch,)))
        payload = dict(schema_version=1,batch_id=batch,messages=[show(store,row["id"],True) for row in rows])
        path = write_private(output, json.dumps(payload,ensure_ascii=False,indent=2).encode())
    return dict(path=path,count=len(rows))
