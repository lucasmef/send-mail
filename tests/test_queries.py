import json
import pytest
from mailqueue.storage import Store
from mailqueue.importer import import_batch
from mailqueue.queries import list_messages, show, cancel, export_batch
from mailqueue.errors import QueueError
from test_cli import call


def test_query_export_and_cancel(configured, batch_file, tmp_path):
    directory, config = configured
    store = Store(directory)
    ids = import_batch(store, config, batch_file)["ids"]
    page = list_messages(store, "fictional-batch", limit=2)
    next_page = list_messages(store,"fictional-batch",limit=2,cursor=page["next_cursor"])
    assert len(next_page["messages"]) == 1
    assert len({row["id"] for row in page["messages"]+next_page["messages"]}) == 3
    assert "html" not in show(store, ids[0])
    assert "html" in show(store,ids[0],True)
    assert cancel(store,ids[0])["state"] == "cancelled"
    with pytest.raises(QueueError):
        cancel(store,ids[0])
    with pytest.raises(QueueError):
        show(store,"absent")
    assert list_messages(store,state="cancelled")["counts"]["cancelled"] == 1
    output = tmp_path / "export.json"
    export_batch(store,"fictional-batch",output)
    exported = json.loads(output.read_text())
    assert len(exported["messages"]) == 3
    assert exported["messages"][0] == show(store,ids[0],True)
    result = call("list","--data-dir",str(directory),"--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert all("html" not in item and "mime_base64" not in item for item in data["messages"])
    assert result.stderr == ""
    store.close()
