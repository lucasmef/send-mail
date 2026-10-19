import csv
import json
import time
import uuid
from pathlib import Path
from .composer import canonical_item, compose, digest, signatures
from .errors import QueueError


def load_batch(filename, batch=None):
    try:
        path = Path(filename)
        if path.suffix.lower() == ".csv":
            if not batch:
                raise QueueError("BATCH_REQUIRED", "CSV exige --batch.")
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                base = ["external_id", "to", "subject", "html", "text"]
                if (not reader.fieldnames or reader.fieldnames[:5] != base
                    or len(reader.fieldnames) != len(set(reader.fieldnames))
                    or set(reader.fieldnames[5:]) - {'sender_name', 'to_name'}):
                    raise QueueError("INVALID_CSV", "Cabeçalho CSV inválido.")
                items = list(reader)
                for item in items:
                    for field in ('sender_name', 'to_name'):
                        if item.get(field) == '': item.pop(field)
        else:
            def unique(pairs):
                out = {}
                for key, value in pairs:
                    if key in out:
                        raise QueueError("INVALID_JSON", "Campo JSON repetido.")
                    out[key] = value
                return out
            document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
            if not isinstance(document, dict) or set(document) != {"schema_version","batch_id","messages"} or type(document["schema_version"]) is not int or document["schema_version"] != 1:
                raise QueueError("INVALID_BATCH", "Formato ou versão do lote inválidos.")
            if batch is not None and batch != document["batch_id"]:
                raise QueueError("INVALID_BATCH", "--batch difere do lote JSON.")
            batch, items = document["batch_id"], document["messages"]
    except (OSError, ValueError, csv.Error):
        raise QueueError("INVALID_FILE", "Não foi possível ler o lote UTF-8.")
    if not isinstance(batch, str) or not batch.strip() or not isinstance(items, list) or not items:
        raise QueueError("INVALID_BATCH", "Lote deve ter ID e mensagens.")
    normalized, errors, seen = [], [], {}
    for index, item in enumerate(items):
        try:
            value = canonical_item(item)
            key, hashed = value["external_id"], digest(value)
            if key in seen and seen[key] != hashed:
                raise QueueError("IDEMPOTENCY_CONFLICT", "ID repetido com conteúdo diferente.", 3)
            seen[key] = hashed
            normalized.append(value)
        except QueueError as exc:
            errors.append(dict(item=index, code=exc.code, **(exc.details or {})))
    if errors:
        conflict = any(e["code"] == "IDEMPOTENCY_CONFLICT" for e in errors)
        raise QueueError("IDEMPOTENCY_CONFLICT" if conflict else "INVALID_BATCH", "Lote recusado; nenhuma mensagem importada.", 3 if conflict else 2, details=errors)
    return batch, normalized


def insert_message(store, values):
    fields = list(values)
    # Os nomes vêm apenas do código; valores da entrada são parametrizados.
    store.db.execute("INSERT INTO messages (" + ",".join(fields) + ") VALUES (" + ",".join("?" for _ in fields) + ")", tuple(values.values()))


def import_batch(store, config, filename, batch=None, validate=False):
    batch, items = load_batch(filename, batch)
    signature = signatures(config)
    if not isinstance(config.get("account_id"), str) or not config["account_id"]:
        raise QueueError("CONFIG_INVALID", "Conta local não configurada.", 4)
    ids, created, reused = [], 0, 0
    # Serializa comparação e inserção entre importadores, nunca envolve rede.
    with store.transaction():
        seen = {}
        for index, item in enumerate(items):
            key = item["external_id"]
            if key in seen:
                ids.append(seen[key]); reused += 1; continue
            row = store.db.execute("SELECT id,input_hash FROM messages WHERE batch_id=? AND external_id=? AND account_id=?", (batch,key,config["account_id"])).fetchone()
            if row:
                if row["input_hash"] != digest(item):
                    raise QueueError("IDEMPOTENCY_CONFLICT", "Esta chave já existe com outro conteúdo.", 3, details={"item":index,"field":"external_id"})
                identity = row["id"]; reused += 1
            else:
                content = compose(item, config, signature)
                identity = "m_" + uuid.uuid4().hex
                now = time.time()
                if not validate:
                    insert_message(store, dict(id=identity,batch_id=batch,external_id=key,account_id=config["account_id"],created_at=now,updated_at=now,**content))
                created += 1
            ids.append(identity); seen[key] = identity
    return dict(batch_id=batch, ids=[] if validate else ids, created=0 if validate else created, would_create=created if validate else 0, reused=reused, valid=True)
