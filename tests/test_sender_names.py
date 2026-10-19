from email import message_from_bytes
from email.policy import default
import json
import pytest
from mailqueue.cli import parser, dispatch
from mailqueue.config import load_config
from mailqueue.composer import compose, canonical_item
from mailqueue.errors import QueueError
from mailqueue.importer import import_batch, load_batch
from mailqueue.storage import Store
from mailqueue.resolution import copy_message

ITEM = dict(external_id='name-1', to='recipient@example.com', subject='Olá', html='<p>Teste</p>')


def test_default_and_override_names_preserve_envelope(configured):
    directory, original = configured
    result = dispatch(parser().parse_args(['sender','--data-dir',str(directory),'--email','contact@example.com','--name','Equipe Padrão']))
    config = load_config(directory)
    assert config['login'] == original['login']
    assert config['account_id'] == original['account_id']
    assert result['sender_name'] == 'Equipe Padrão'
    for extra, name in [({}, 'Equipe Padrão'), ({'sender_name':'Outra, Equipe','to_name':'José Silva'},'Outra, Equipe')]:
        message = compose({**ITEM, **extra}, config)
        mime = message_from_bytes(message['mime_bytes'],policy=default)
        assert mime['From'].addresses[0].display_name == name
        assert mime['From'].addresses[0].addr_spec == message['sender'] == 'contact@example.com'
        assert mime['To'].addresses[0].addr_spec == message['recipient'] == ITEM['to']
        assert mime['To'].addresses[0].display_name == extra.get('to_name','')


@pytest.mark.parametrize('field',['sender_name','to_name'])
def test_names_reject_injection(field):
    with pytest.raises(QueueError): canonical_item({**ITEM,field:'Name\r\nBcc: other@example.com'})


def test_frozen_names_and_test_destination(configured, tmp_path):
    directory, config = configured
    file = tmp_path/'batch.json'
    file.write_text(json.dumps(dict(schema_version=1,batch_id='names',messages=[{**ITEM,'to_name':'Pessoa Original'}])))
    config['sender_name']='Primeiro'
    store=Store(directory)
    try:
        identity=import_batch(store,config,file)['ids'][0]
        before=store.get_message(identity)['mime_bytes']
        config['sender_name']='Segundo'
        assert import_batch(store,config,file)['reused']==1
        assert store.get_message(identity)['mime_bytes']==before
        with store.transaction():
            clone,_=copy_message(store,identity,'clone',['clone'])
            test,_=copy_message(store,identity,'test',['test'],'test@example.com','test')
        clone_mime=message_from_bytes(store.get_message(clone)['mime_bytes'],policy=default)
        test_mime=message_from_bytes(store.get_message(test)['mime_bytes'],policy=default)
        assert clone_mime['To'].addresses[0].display_name=='Pessoa Original'
        assert test_mime['To'].addresses[0].display_name==''
        assert test_mime['To'].addresses[0].addr_spec=='test@example.com'
        assert test_mime['From'].addresses[0].display_name=='Primeiro'
    finally: store.close()


def test_csv_names(tmp_path):
    file=tmp_path/'names.csv'
    file.write_text('external_id,to,subject,html,text,sender_name,to_name\n1,a@example.com,Oi,<p>Oi</p>,,Equipe,José\n2,b@example.com,Oi,<p>Oi</p>,,,\n')
    _,items=load_batch(file,'names')
    assert items[0]['sender_name']=='Equipe'
    assert items[0]['to_name']=='José'
    assert 'sender_name' not in items[1]
