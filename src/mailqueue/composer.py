import hashlib
import html as html_module
import json
import re
import uuid
from email.message import EmailMessage
from email.headerregistry import Address
from email.policy import SMTP
from email.utils import formatdate
from html.parser import HTMLParser
from pathlib import Path
from .errors import QueueError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def header(value, field):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\x00"):
        raise QueueError("INVALID_HEADER", "Cabeçalho inválido.", details={"field": field})
    return value


def address(value):
    header(value, "email")
    if value.count("@") != 1:
        raise QueueError("INVALID_ADDRESS", "Informe um único endereço simples.")
    local, domain = value.split("@")
    if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+", local) or len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
        raise QueueError("INVALID_ADDRESS", "Parte local do endereço inválida ou fora do escopo ASCII.")
    try:
        domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise QueueError("INVALID_ADDRESS", "Domínio inválido.")
    labels = domain.split(".")
    if len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels) or len(domain) > 253:
        raise QueueError("INVALID_ADDRESS", "Domínio inválido.")
    return local + "@" + domain


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden, self.links = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template"):
            self.hidden += 1
        if self.hidden:
            return
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2"):
            self.parts.append("\n")
        if tag == "a":
            self.links.append(dict(attrs).get("href", ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template"):
            self.hidden = max(0, self.hidden-1)
            return
        if self.hidden:
            return
        if tag == "a" and self.links:
            link = self.links.pop()
            if link.startswith(("https://", "http://", "mailto:")):
                self.parts.append(" (" + link + ")")
        if tag in ("p", "div", "li", "tr", "h1", "h2"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def to_text(content):
    parser = TextParser()
    parser.feed(content)
    return re.sub(r"\n[ \t]*\n+", "\n\n", "".join(parser.parts)).strip()


def signatures(config):
    try:
        return (Path(config["signature_html"]).read_text(encoding="utf-8"), Path(config["signature_text"]).read_text(encoding="utf-8"))
    except (OSError, KeyError):
        raise QueueError("SIGNATURE_MISSING", "Configure arquivos locais de assinatura HTML e texto.", 4)


def canonical_item(item):
    required = {"external_id", "to", "subject", "html"}
    if not isinstance(item, dict) or not required <= item.keys() or item.keys() - required - {"text", "sender_name", "to_name"}:
        raise QueueError("INVALID_ITEM", "Campos ausentes ou não documentados.")
    for field in required | ({"text"} if "text" in item else set()):
        if not isinstance(item[field], str) or (field != "text" and not item[field].strip()) or "\x00" in item[field]:
            raise QueueError("INVALID_FIELD", "Campo inválido.", details={"field": field})
    result = dict(item)
    for field in ("sender_name", "to_name"):
        if field in result:
            result[field] = header(result[field], field).strip()
    result["to"] = address(item["to"])
    result["subject"] = header(item["subject"], "subject")
    if not result.get("text"):
        result.pop("text", None)
    return result


def append_once(body, signature, separator):
    body, signature = body.rstrip(), signature.strip()
    return body if not signature or body.endswith(signature) else body + separator + signature


def compose(item, config, signature=None):
    item = canonical_item(item)
    sender = address(config["sender"])
    sig_html, sig_text = signatures(config) if signature is None else signature
    final_html = append_once(item["html"], sig_html, "\n")
    final_text = append_once(item.get("text", to_text(item["html"])), sig_text, "\n\n")
    message = EmailMessage(policy=SMTP)
    sender_name = item.get("sender_name", config.get("sender_name", ""))
    if sender_name:
        sender_name = header(sender_name, "sender_name").strip()
    message["From"] = Address(display_name=sender_name, addr_spec=sender)
    message["To"] = Address(display_name=item.get("to_name", ""), addr_spec=item["to"])
    message["Subject"] = item["subject"]
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = "<" + uuid.uuid4().hex + "@" + sender.split("@")[1] + ">"
    message.set_content(final_text, charset="utf-8")
    message.add_alternative(final_html, subtype="html", charset="utf-8")
    return dict(sender=sender, recipient=item["to"], subject=item["subject"], html=final_html, text=final_text,
                message_id=str(message["Message-ID"]), mime_bytes=message.as_bytes(),
                input_hash=digest(item), content_hash=digest([str(message["From"]),str(message["To"]),item["subject"],final_html,final_text]))
