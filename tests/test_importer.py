import csv
import json
import subprocess
import sys
import pytest
from mailqueue.storage import Store
from mailqueue.importer import import_batch
from mailqueue.errors import QueueError


def test_atomic_idempotent_freeze(configured, batch_file):
    directory, config = configured
    store = Store(directory)
    assert import_batch(store, config, batch_file, validate=True)["would_create"] == 3
    assert store.db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
    result = import_batch(store, config, batch_file)
    before = list(store.db.execute("SELECT mime_bytes FROM messages ORDER BY id"))
    (directory / "signature.html").write_text("<p>Outra assinatura</p>")
    assert import_batch(store, config, batch_file)["ids"] == result["ids"]
    assert [r[0] for r in before] == [r[0] for r in store.db.execute("SELECT mime_bytes FROM messages ORDER BY id")]
    document = json.loads(batch_file.read_text())
    document["messages"].insert(0, {**document["messages"][0],"external_id":"new"})
    document["messages"][-1]["subject"] = "Alterado"
    batch_file.write_text(json.dumps(document))
    with pytest.raises(QueueError) as err:
        import_batch(store, config, batch_file)
    assert err.value.code == "IDEMPOTENCY_CONFLICT"
    assert store.db.execute("SELECT count(*) FROM messages").fetchone()[0] == 3
    document["messages"][-1]["to"] = "invalid"
    batch_file.write_text(json.dumps(document))
    with pytest.raises(QueueError) as err:
        import_batch(store, config, batch_file)
    assert err.value.details[0]["item"] == 3
    assert store.db.execute("SELECT count(*) FROM messages").fetchone()[0] == 3
    store.close()


def test_duplicate_and_csv(configured, batch_file, tmp_path):
    directory, config = configured
    store = Store(directory)
    doc = json.loads(batch_file.read_text())
    doc["messages"].append(doc["messages"][0])
    batch_file.write_text(json.dumps(doc))
    assert import_batch(store, config, batch_file)["reused"] == 1
    file = tmp_path / "batch.csv"
    with file.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["external_id","to","subject","html","text"])
        writer.writeheader()
        writer.writerow(dict(external_id="csv",to="person@example.com",subject='Aspas, "ação"',html='<p>Oi, "pessoa"\nTudo bem?</p>',text=""))
    assert import_batch(store, config, file, "csv")["created"] == 1
    row = store.db.execute("SELECT subject,html FROM messages WHERE batch_id='csv'").fetchone()
    assert row["subject"] == 'Aspas, "ação"'
    assert "\nTudo bem?" in row["html"]
    store.close()


def test_concurrent_import(configured, batch_file):
    directory, _ = configured
    cmd = [sys.executable, "-m", "mailqueue.cli", "--data-dir", str(directory), "import", str(batch_file)]
    procs = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    outputs = [proc.communicate(timeout=10) for proc in procs]
    assert all(proc.returncode == 0 for proc in procs), outputs
    assert sum(json.loads(out)["data"]["created"] for out, _ in outputs) == 3
    store = Store(directory)
    assert store.db.execute("SELECT count(*) FROM messages").fetchone()[0] == 3
    store.close()
