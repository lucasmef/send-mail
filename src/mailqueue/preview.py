import html
import uuid
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from .queries import write_private

# Lista positiva: sem CSS, mídia, atributos arbitrários ou recursos remotos.
ALLOWED = {"p","div","span","br","hr","strong","b","em","i","u","s","blockquote","pre","code","ul","ol","li","table","thead","tbody","tr","th","td","h1","h2","h3","h4","a"}
HIDDEN = {"script","style","iframe","object","template","form","svg","math","noscript"}
VOID = {"br","hr"}


class Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output, self.hidden = [], []

    def handle_starttag(self, tag, attrs):
        if tag in HIDDEN:
            self.hidden.append(tag)
        if self.hidden or tag not in ALLOWED:
            return
        attribute = ""
        if tag == "a":
            link = dict(attrs).get("href", "")
            try:
                safe_scheme=urlsplit(link).scheme.lower() in ('https','http','mailto')
            except ValueError:
                safe_scheme=False
            if not any(ord(c)<32 for c in link) and safe_scheme:
                attribute = ' href="' + html.escape(link,quote=True) + '" rel="noreferrer noopener"'
        self.output.append("<" + tag + attribute + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag in ALLOWED and tag not in VOID:
            self.output.append("</" + tag + ">")

    def handle_data(self, data):
        if not self.hidden:
            self.output.append(html.escape(data))


def protected_html(row):
    sanitizer = Sanitizer()
    sanitizer.feed(row["html"])
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'none\'; style-src \'none\'; img-src \'none\'; frame-src \'none\'; form-action \'none\'; base-uri \'none\'">'
            '<meta name="referrer" content="no-referrer"><title>Preview local</title></head><body>'
            '<h1>' + html.escape(row["subject"]) + '</h1>' + "".join(sanitizer.output) + '</body></html>').encode()


def preview(store, identity, format, output=None):
    row = store.get_message(identity)
    content = row["mime_bytes"] if format == "eml" else protected_html(row)
    if output is None:
        directory = store.path.parent / "previews"
        directory.mkdir(mode=0o700,exist_ok=True)
        directory.chmod(0o700)
        output = directory / (identity + "-" + uuid.uuid4().hex + "." + format)
    return dict(path=write_private(output,content),format=format,message_id=identity)
