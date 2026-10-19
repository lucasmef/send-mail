import json
import pytest
from mailqueue.storage import Store


@pytest.fixture
def configured(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    (directory / "signature.html").write_text("<p>Equipe fictícia</p>")
    (directory / "signature.txt").write_text("Equipe fictícia")
    config = dict(schema_version=1, account_id="fictional", login="fictional@icloud.com", sender="sender@example.com", signature_html=str(directory/"signature.html"), signature_text=str(directory/"signature.txt"), interval_seconds=15, daily_budget=100)
    (directory / "config.json").write_text(json.dumps(config))
    return directory, config


@pytest.fixture
def batch_file(tmp_path):
    items = [dict(external_id=str(i), to="person@example.com", subject="Olá", html="<p>Olá, fictício</p>") for i in range(3)]
    file = tmp_path / "batch.json"
    file.write_text(json.dumps(dict(schema_version=1, batch_id="fictional-batch", messages=items)))
    return file


@pytest.fixture(autouse=True)
def no_real_smtp(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('Rede SMTP real proibida nos testes.')
    monkeypatch.setattr('smtplib.SMTP',forbidden)
    monkeypatch.setattr('smtplib.SMTP_SSL',forbidden)


@pytest.fixture(autouse=True)
def no_real_imap(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Rede IMAP real proibida nos testes.')
    monkeypatch.setattr('imaplib.IMAP4_SSL', forbidden)
