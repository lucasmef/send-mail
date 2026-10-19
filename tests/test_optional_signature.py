import pytest
import json
from mailqueue.composer import digest
from mailqueue.config import load_config
from mailqueue.setup import setup, configure_signature
from mailqueue import credentials
from mailqueue.errors import QueueError
from mailqueue.importer import import_batch
from mailqueue.storage import Store
from mailqueue.cli import parser, dispatch


def test_setup_preserves_existing_preferences(configured, monkeypatch):
    directory, original = configured
    original['account_id'] = 'a_' + digest(original['login'])[:24]
    (directory / 'config.json').write_text(json.dumps(original))
    monkeypatch.setattr('builtins.input', lambda: original['login'])
    monkeypatch.setattr(credentials, 'secure_password', lambda *args: 'test-' + __import__('uuid').uuid4().hex)
    monkeypatch.setattr(credentials, 'save', lambda *args: None)
    setup(directory)
    assert load_config(directory) == {**original, 'provider':'icloud'}
    assert (directory / 'signature.html').read_text() == '<p>Equipe fictícia</p>'
    setup(directory, sender='other@example.com')
    assert load_config(directory)['sender'] == 'other@example.com'


def test_signature_change_and_clear_only_affect_new_imports(configured, batch_file, tmp_path):
    directory, config = configured
    store = Store(directory)
    try:
        import_batch(store, config, batch_file)
        before = [tuple(row) for row in store.db.execute('SELECT id,mime_bytes FROM messages ORDER BY id')]
        source = tmp_path / 'new.html'
        source.write_text('<p>Nova assinatura</p>')
        result = dispatch(parser().parse_args(['signature', '--data-dir', str(directory), '--html', str(source), '--json']))
        assert result['applies_to'] == 'future_imports'
        updated = load_config(directory)
        from mailqueue.composer import signatures, compose
        assert signatures(updated) == ('<p>Nova assinatura</p>', 'Nova assinatura')
        import_batch(store, updated, batch_file)
        assert [tuple(row) for row in store.db.execute('SELECT id,mime_bytes FROM messages ORDER BY id')] == before
        item = dict(external_id='one', to='person@example.com', subject='Teste', html='<p>Corpo</p>')
        assert 'Nova assinatura' in compose(item, updated)['html']
        dispatch(parser().parse_args(['signature', '--data-dir', str(directory), '--clear']))
        assert compose(item, load_config(directory))['html'] == '<p>Corpo</p>'
    finally:
        store.close()


def test_invalid_signature_keeps_configuration(configured, tmp_path):
    directory, original = configured
    with pytest.raises(QueueError):
        configure_signature(directory, html=tmp_path/'missing.html')
    with pytest.raises(QueueError):
        configure_signature(directory, text=tmp_path/'missing.txt', clear=True)
    assert load_config(directory) == original
