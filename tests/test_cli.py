import json
import subprocess
import sys


def call(*args):
    return subprocess.run([sys.executable, "-m", "mailqueue.cli", *args], capture_output=True, text=True)


def test_help():
    result = call("--help")
    assert result.returncode == 0
    assert "mailqueue" in result.stdout
    assert result.stderr == ""


def test_invalid_json(tmp_path):
    result = call("--data-dir", str(tmp_path), "not-a-command", "--json")
    assert result.returncode == 2
    output = json.loads(result.stdout)
    assert output["schema_version"] == 1
    assert output["error"]["code"] == "INVALID_ARGUMENT"
    assert result.stderr == ""


def test_config_contract(tmp_path,configured):
    from mailqueue.config import load_config, data_path
    from mailqueue.errors import QueueError
    import pytest
    assert data_path(tmp_path) == tmp_path
    with pytest.raises(QueueError, match="Configure"):
        load_config(tmp_path)
    directory,config=configured
    assert load_config(directory)["account_id"]=="fictional"
    (tmp_path / "config.json").write_text('{"schema_version":1,"account_id":"fictional"}')
    with pytest.raises(QueueError): load_config(tmp_path)
