from email import message_from_bytes
from email.policy import default
import pytest
from mailqueue.composer import compose, canonical_item, address, to_text
from mailqueue.errors import QueueError

ITEM = dict(external_id="fictional-1", to="Pessoa+tag@exämple.com", subject="Olá, atualização", html='<p>Ação &amp; atenção</p><p><a href="https://example.com">Link</a></p>')


def test_mime_signature_and_idna():
    result = compose(ITEM, {"sender":"sender@example.com"}, ("<p>Assinatura</p>", "Assinatura"))
    mime = message_from_bytes(result["mime_bytes"], policy=default)
    assert mime["To"] == "Pessoa+tag@xn--exmple-cua.com"
    assert mime["Subject"] == ITEM["subject"]
    assert mime["Message-ID"] == result["message_id"]
    assert mime.get_body(preferencelist=("html",)).get_content().count("<p>Assinatura</p>") == 1
    assert "Ação & atenção" in mime.get_body(preferencelist=("plain",)).get_content()
    assert "https://example.com" in result["text"]
    item = {**ITEM,"html":result["html"],"text":result["text"]}
    again = compose(item, {"sender":"sender@example.com"}, ("<p>Assinatura</p>", "Assinatura"))
    assert again["html"] == result["html"]
    assert again["text"] == result["text"]


@pytest.mark.parametrize("email", ["a@example.com,b@example.com", "Pessoa <a@example.com>", "á@example.com", "a\n@example.com", ".a@example.com", "a@invalid", "a@-bad.com"])
def test_reject_address(email):
    with pytest.raises(QueueError):
        address(email)


def test_reject_header_injection():
    with pytest.raises(QueueError):
        canonical_item({**ITEM, "subject":"Oi\r\nBcc: other@example.com"})
    assert "alert" not in to_text("<p>Olá</p><script>alert(1)</script>")
