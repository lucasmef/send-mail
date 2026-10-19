from pathlib import Path
from html.parser import HTMLParser
from mailqueue.preview import protected_html, preview
from mailqueue.storage import Store
from mailqueue.importer import import_batch


def test_protected_html():
    hostile = """<script>alert(1)</script><p onclick="alert(2)" style="background:url(https://example.com/x)">Olá</p><img src="https://example.com/x"><form action="https://example.com"><input></form><iframe src="https://example.com"></iframe><meta http-equiv="refresh" content="0;url=https://example.com"><link rel="stylesheet" href="https://example.com"><svg><a href="javascript:alert(1)">SVG</a></svg><a href="javascript:alert(1)">inseguro</a><a href="https://example.com">Link</a>"""
    output = protected_html(dict(subject="<Ataque>",html=hostile)).decode()
    class Audit(HTMLParser):
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            assert tag not in {"script","img","iframe","form","input","link","svg"}
            assert not any(k.startswith("on") or k in {"src","style"} for k in attrs)
            if tag=="meta":
                assert attrs.get("http-equiv","").lower() != "refresh"
            assert not attrs.get("href","").startswith("javascript:")
    Audit().feed(output)
    assert "default-src 'none'" in output
    assert "&lt;Ataque&gt;" in output
    assert "Olá" in output


def test_preview_frozen_eml_no_attempt(configured,batch_file):
    directory,config=configured
    store=Store(directory)
    identity=import_batch(store,config,batch_file)["ids"][0]
    original=store.get_message(identity)["mime_bytes"]
    eml=preview(store,identity,"eml")
    html=preview(store,identity,"html")
    assert Path(eml["path"]).is_absolute()
    assert Path(eml["path"]).read_bytes()==original
    assert Path(html["path"]).stat().st_mode & 0o777 == 0o600
    assert store.db.execute("SELECT count(*) FROM attempts").fetchone()[0]==0
    assert store.get_message(identity)["state"]=="pending"
    store.close()
