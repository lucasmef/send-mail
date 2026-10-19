"""Arquivo IMAP independente: nunca chama SMTP nem altera messages."""
import contextlib
from email import policy
from email.parser import BytesParser
import imaplib
import json
import re
import ssl
import time
import certifi
from . import credentials
from .errors import QueueError

HOST = 'imap.kinghost.net'
PORT = 993


def validate_settings(config):
    settings = config.get('archive')
    if settings is None:
        return
    if (config.get('provider') != 'kinghost' or not isinstance(settings, dict)
            or set(settings) != {'folder'} or not isinstance(settings['folder'], str)
            or not settings['folder'] or not settings['folder'].isascii()
            or any(ord(c) < 32 or ord(c) == 127 for c in settings['folder'])):
        raise QueueError('CONFIG_INVALID', 'Configuração IMAP inválida; pasta usa nome IMAP ASCII ou UTF-7 modificado.', 4)


def quoted(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def require_ok(result, code='IMAP_COMMAND_FAILED'):
    if result[0] != 'OK':
        raise QueueError(code, 'Operação IMAP recusada; nenhuma resposta bruta registrada.', 4)
    return result[1]


class IMAPArchive:
    def __init__(self, config, factory=None):
        self.config = config
        self.factory = factory or imaplib.IMAP4_SSL
        self.session = None

    def connect(self):
        context = ssl.create_default_context(cafile=certifi.where())
        self.session = self.factory(HOST, PORT, ssl_context=context, timeout=30)
        secret = credentials.retrieve(self.config['login'])
        try:
            try:
                require_ok(self.session.login(self.config['login'], secret), 'IMAP_AUTH_FAILED')
            except imaplib.IMAP4.error:
                raise QueueError('IMAP_AUTH_FAILED', 'Autenticação IMAP recusada.', 4) from None
        finally:
            secret = None

    def close(self):
        if self.session is not None:
            with contextlib.suppress(Exception):
                self.session.logout()
            self.session = None

    def folders(self):
        rows = require_ok(self.session.list())
        folders = []
        # Nomes literais (raros) são reconstruídos sem interpretar conteúdo.
        for row in rows:
            if isinstance(row, tuple):
                head, literal = row
                row = head.rsplit(b' ', 1)[0] + b' ' + literal
            if not isinstance(row, bytes):
                continue
            match = re.fullmatch(rb'\(([^)]*)\) (NIL|"(?:[^"\\]|\\.)*") (.+)', row)
            if not match:
                raise QueueError('IMAP_LIST_INVALID', 'Não foi possível interpretar a lista de pastas.', 4)
            flags, delimiter, name = match.groups()
            def unquote(value):
                if value.startswith(b'"') and value.endswith(b'"'):
                    return re.sub(rb'\\(.)', rb'\1', value[1:-1]).decode('ascii')
                return value.decode('ascii')
            folders.append(dict(name=unquote(name), flags=flags.decode('ascii').split(),
                                delimiter=None if delimiter == b'NIL' else unquote(delimiter)))
        return folders

    def select(self, folder):
        require_ok(self.session.select(quoted(folder), readonly=True), 'IMAP_FOLDER_UNAVAILABLE')
        response = self.session.response('UIDVALIDITY')[1]
        return response[0].decode('ascii') if response and response[0] else None

    def find(self, message_id):
        data = require_ok(self.session.uid('SEARCH', None, 'HEADER', 'Message-ID', quoted(message_id)))
        exact = []
        for uid in b' '.join(item for item in data if isinstance(item, bytes)).split():
            headers = require_ok(self.session.uid('FETCH', uid, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])'))
            for item in headers:
                if isinstance(item, tuple):
                    msg = BytesParser(policy=policy.default).parsebytes(item[1])
                    values = [re.sub(r'\r?\n[ \t]+', ' ', value).strip()
                              for key, value in msg.raw_items() if key.lower() == 'message-id']
                    if values == [message_id]:
                        exact.append(uid.decode('ascii'))
        return exact

    def append(self, folder, wire_bytes, sent_at):
        return self.session.append(quoted(folder), r'\Seen', imaplib.Time2Internaldate(sent_at), wire_bytes)


def error_code(exc):
    if isinstance(exc, QueueError):
        return exc.code
    if isinstance(exc, ssl.SSLError):
        return 'IMAP_TLS_INVALID'
    if isinstance(exc, imaplib.IMAP4.error):
        return 'IMAP_PROTOCOL_FAILED'
    return 'IMAP_CONNECTION_FAILED'


def archive_status(store, identity):
    store.get_message(identity)
    row = store.db.execute('SELECT * FROM archives WHERE message_id=?', (identity,)).fetchone()
    if row is None:
        return dict(state='not_requested')
    return {key: row[key] for key in ('state', 'folder', 'attempts', 'last_error_code',
                                     'created_at', 'updated_at', 'archived_at', 'uid', 'uidvalidity')}


def record_accepted(store, message, config, now):
    if config.get('archive'):
        store.db.execute("""INSERT INTO archives(message_id,state,folder,wire_bytes,created_at,updated_at)
                            VALUES(?,'pending',?,?,?,?)""",
                         (message['id'], config['archive']['folder'],
                          message.get('wire_bytes', message['mime_bytes']), now, now))


def retry_archive(store, config, identity, transport=None):
    """Chamador mantém worker_lock. Uma ausência após APPEND incerto não autoriza repetir."""
    message = store.get_message(identity)
    row = store.db.execute('SELECT * FROM archives WHERE message_id=?', (identity,)).fetchone()
    if row is None:
        raise QueueError('ARCHIVE_NOT_REQUESTED', 'Nenhum arquivo solicitado para esta mensagem; histórico não é arquivado automaticamente.', 3)
    if message['state'] != 'sent' or message['account_id'] != config['account_id']:
        raise QueueError('ARCHIVE_ACCOUNT_CONFLICT', 'Arquivo exige mensagem enviada pela conta ativa.', 3)
    if row['state'] == 'archived':
        return archive_status(store, identity)
    store.ensure_sendable()
    uncertain = row['state'] in ('appending', 'uncertain')
    state = 'uncertain' if uncertain else row['state']
    def save(new_state, code=None, uid=None, validity=None):
        with store.transaction():
            store.db.execute('UPDATE archives SET state=?,last_error_code=?,updated_at=?,archived_at=?,uid=?,uidvalidity=? WHERE message_id=?',
                             (new_state, code, time.time(), time.time() if new_state == 'archived' else None, uid, validity, identity))
    if uncertain:
        save('uncertain', 'IMAP_UNCERTAIN')
    client = transport or IMAPArchive(config)
    try:
        client.connect()
        validity = client.select(row['folder'])
        matches = client.find(message['message_id'])
        if matches:
            if len(matches) > 1:
                save('uncertain', 'IMAP_DUPLICATES_FOUND', validity=validity)
            else:
                save('archived', uid=matches[0], validity=validity)
        elif uncertain:
            save('uncertain', 'IMAP_UNCERTAIN_NOT_FOUND', validity=validity)
        else:
            with store.transaction():
                store.db.execute("UPDATE archives SET state='appending',attempts=attempts+1,last_error_code=NULL,updated_at=? WHERE message_id=?", (time.time(), identity))
            state = 'appending'
            result = client.append(row['folder'], row['wire_bytes'], message['sent_at'])
            if result[0] == 'OK':
                # APPENDUID é opcional; aceitação final positiva é suficiente.
                save('archived', validity=validity)
            elif result[0] in ('NO', 'BAD'):
                save('failed', 'IMAP_APPEND_REJECTED', validity=validity)
            else:
                save('uncertain', 'IMAP_UNCERTAIN', validity=validity)
    except Exception as exc:
        # Sem resposta positiva/negativa após APPEND, não assumir falha segura.
        save('uncertain' if state == 'appending' or uncertain else 'failed', error_code(exc))
    finally:
        with contextlib.suppress(Exception):
            client.close()
    return archive_status(store, identity)


def configure(directory, action, folder=None, create=False, factory=None):
    from .config import load_config
    from .setup import atomic_private
    from .worker import worker_lock
    if (folder is not None or create) and action != 'configure':
        raise QueueError('INVALID_ARGUMENT', '--folder/--create exigem archive configure.')
    if create and not folder:
        raise QueueError('INVALID_ARGUMENT', '--create exige nome de pasta explícito.')
    with worker_lock(directory):
        config = load_config(directory)
        if config.get('provider') != 'kinghost':
            raise QueueError('IMAP_PROVIDER_UNSUPPORTED', 'Arquivo IMAP disponível para KingHost direto.', 4)
        if folder is not None:
            validate_settings(dict(config, archive=dict(folder=folder)))
        if action == 'disable':
            config.pop('archive', None)
            atomic_private(directory/'config.json', json.dumps(config, ensure_ascii=False, indent=2).encode())
            return dict(enabled=False)
        client = IMAPArchive(config, factory)
        try:
            client.connect()
            folders = client.folders()
            selected = folder or (config.get('archive') or {}).get('folder')
            if selected is None:
                sent = [f['name'] for f in folders if '\\Sent' in f['flags'] and '\\Noselect' not in f['flags']]
                if len(sent) == 1:
                    selected = sent[0]
            if selected is None:
                return dict(enabled=False, host=HOST, port=PORT, tls='verified', authentication='ok',
                            folder=None, folders=folders, needs_folder=True, appended=False)
            names = [f['name'] for f in folders if '\\Noselect' not in f['flags']]
            if selected not in names:
                if not create:
                    raise QueueError('IMAP_FOLDER_UNAVAILABLE', 'Pasta não existe; escolha uma pasta listada ou solicite criação explícita.', 4, details=dict(folders=folders))
                require_ok(client.session.create(quoted(selected)), 'IMAP_CREATE_FAILED')
                require_ok(client.session.subscribe(quoted(selected)), 'IMAP_SUBSCRIBE_FAILED')
                folders = client.folders()
                if selected not in [f['name'] for f in folders]:
                    raise QueueError('IMAP_FOLDER_UNAVAILABLE', 'Pasta criada não apareceu na lista.', 4)
            validate_settings(dict(config, archive=dict(folder=selected)))
            validity = client.select(selected)
            if action == 'configure':
                config['archive'] = dict(folder=selected)
                atomic_private(directory/'config.json', json.dumps(config, ensure_ascii=False, indent=2).encode())
            return dict(enabled=bool(config.get('archive')), host=HOST, port=PORT, tls='verified', authentication='ok',
                        folder=selected, uidvalidity=validity, folders=folders, appended=False)
        except (OSError, imaplib.IMAP4.error) as exc:
            raise QueueError(error_code(exc), 'Verificação IMAP falhou; confira conta, TLS e conexão.', 4) from None
        finally:
            client.close()
