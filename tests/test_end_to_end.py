import base64
import json
from pathlib import Path
import sqlite3
import subprocess
import sys


def invoke(directory,*args,scenario='ok',expected=0):
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('cli_driver.py')),scenario,'--data-dir',str(directory),*args,'--json'],capture_output=True,text=True,timeout=10)
    assert result.returncode==expected,(result.stdout,result.stderr)
    assert result.stderr=='',result.stderr
    output=json.loads(result.stdout)
    assert output['schema_version']==1
    return output['data'] if output['ok'] else output['error']


def test_complete_cli_flow(configured,batch_file,tmp_path):
    directory,_=configured
    assert invoke(directory,'validate',str(batch_file))['would_create']==3
    imported=invoke(directory,'import',str(batch_file)); source=imported['ids'][0]
    assert invoke(directory,'import',str(batch_file))['reused']==3
    assert len(invoke(directory,'list','--batch','fictional-batch')['messages'])==3
    detail=invoke(directory,'show',source,'--include-body')
    html=invoke(directory,'preview',source,'--format','html')
    eml=invoke(directory,'preview',source,'--format','eml')
    assert Path(html['path']).exists()
    assert Path(eml['path']).read_bytes()==base64.b64decode(detail['mime_base64'])
    assert invoke(directory,'doctor')['sent'] is False
    copy=invoke(directory,'test',source,'--to','test@example.com','--request-id','cli-test')
    assert copy['message']['state']=='sent'
    assert invoke(directory,'test',source,'--to','test@example.com','--request-id','cli-test')['message']['id']==copy['message']['id']
    assert invoke(directory,'show',source)['state']=='pending'
    paused=invoke(directory,'run','--batch','fictional-batch','--limit','3','--request-id','cli-run',scenario='pause')
    assert paused['state']=='paused' and paused['attempts_started']==1
    summary=invoke(directory,'status','--run',paused['run_id'])
    assert 'html' not in summary and summary['counts']['sent']==1
    resumed=invoke(directory,'resume','--run',paused['run_id'])
    assert resumed['state']=='completed' and resumed['history']['attempts']==3
    repeated=invoke(directory,'run','--batch','fictional-batch','--limit','3','--request-id','cli-run')
    assert repeated['history']['attempts']==3
    exported=invoke(directory,'export','--batch','fictional-batch','--output',str(tmp_path/'export.json'))
    assert exported['count']==4
    backup=invoke(directory,'backup','--output',str(tmp_path/'copy.db'))
    connection=sqlite3.connect(backup['path'])
    assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert connection.execute("SELECT count(*) FROM messages WHERE state='sent'").fetchone()[0]==4
    connection.close()


def test_cli_auth_failure_contract(configured,batch_file):
    directory,_=configured
    invoke(directory,'import',str(batch_file))
    error=invoke(directory,'run','--batch','fictional-batch','--limit','1','--request-id','cli-auth',scenario='auth',expected=4)
    assert error['code']=='AUTH_FAILED'
    assert error['details']['state']=='blocked'
    assert error['details']['attempts_started']==1
