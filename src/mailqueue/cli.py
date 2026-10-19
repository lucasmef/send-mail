import argparse
import json
import sys
import sqlite3
from .config import data_path
from .errors import QueueError


class Parser(argparse.ArgumentParser):
    def __init__(self,*args,**kwargs):
        kwargs['add_help']=False
        super().__init__(*args,**kwargs)
        self._positionals.title='argumentos'
        self._optionals.title='opções'
        self.add_argument('-h','--help',action='help',help='Exibe esta ajuda e encerra.')

    def error(self, message):
        raise QueueError("INVALID_ARGUMENT", "Argumentos inválidos. Consulte --help.")


def parser():
    p = Parser(prog="mailqueue", description="Fila local de e-mails. Saídas operacionais em JSON v1.")
    p.add_argument("--data-dir")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", action="version", version="mailqueue 0.1.0", help="Exibe a versão e encerra.")
    subs = p.add_subparsers(dest="command", required=True, parser_class=Parser)
    sub = subs.add_parser('dkim', help='Prepara, verifica ou desativa DKIM local sem enviar.')
    sub.add_argument('action', choices=('setup','status','enable','disable'))
    sub.add_argument('--json', action='store_true')
    sub.add_argument('--data-dir', default=argparse.SUPPRESS)
    sub = subs.add_parser('archive', help='Configura/verifica IMAP ou tenta somente o arquivamento; nunca envia SMTP.')
    sub.add_argument('action', choices=('configure','check','disable','status','retry'))
    sub.add_argument('id', nargs='?')
    sub.add_argument('--folder')
    sub.add_argument('--create', action='store_true')
    sub.add_argument('--json', action='store_true')
    sub.add_argument('--data-dir', default=argparse.SUPPRESS)
    b = subs.add_parser("backup", help="Cria backup consistente bloqueado para envio.")
    b.add_argument("--output", required=True)
    b.add_argument("--json", action="store_true")
    b.add_argument("--data-dir", default=argparse.SUPPRESS)
    for name in ("validate", "import"):
        sub = subs.add_parser(name, help="Valida lote sem enviar." if name == "validate" else "Importa lote sem enviar.")
        sub.add_argument("file")
        sub.add_argument("--batch")
        sub.add_argument("--json", action="store_true")
        sub.add_argument("--data-dir", default=argparse.SUPPRESS)
    for name in ("list", "show", "cancel", "export"):
        sub = subs.add_parser(name, help="Consulta ou organiza a fila sem enviar.")
        sub.add_argument("--json", action="store_true")
        sub.add_argument("--data-dir", default=argparse.SUPPRESS)
        if name in ("show", "cancel"):
            sub.add_argument("id")
        if name == "show":
            sub.add_argument("--include-body", action="store_true")
        if name in ("list", "export"):
            sub.add_argument("--batch", required=name == "export")
        if name == "list":
            sub.add_argument("--state")
            sub.add_argument("--limit", type=int, default=20)
            sub.add_argument("--cursor")
        if name == "export":
            sub.add_argument("--output", required=True)
    sub = subs.add_parser("preview", help="Exporta HTML protegido ou EML sem enviar.")
    sub.add_argument("id")
    sub.add_argument("--format", choices=("html", "eml"), default="html")
    sub.add_argument("--output")
    sub.add_argument("--json", action="store_true")
    sub.add_argument("--data-dir", default=argparse.SUPPRESS)
    sub = subs.add_parser("sender", help="Configura endereço/nome do remetente sem alterar login ou senha.")
    sub.add_argument("--email")
    sub.add_argument("--name")
    sub.add_argument("--json", action="store_true")
    sub.add_argument("--data-dir", default=argparse.SUPPRESS)
    for name in ("status","pause"):
        sub = subs.add_parser(name, help="Consulta execução." if name == "status" else "Solicita pausa cooperativa.")
        sub.add_argument("--run", required=True)
        sub.add_argument("--json", action="store_true")
        sub.add_argument("--data-dir", default=argparse.SUPPRESS)
    sub = subs.add_parser("resolve", help="Resolve resultado incerto com motivo auditável.")
    sub.add_argument("id")
    sub.add_argument("--action", choices=("mark-sent","cancel","resend"), required=True)
    sub.add_argument("--reason", required=True)
    sub.add_argument("--request-id")
    sub.add_argument("--json", action="store_true")
    sub.add_argument("--data-dir", default=argparse.SUPPRESS)
    sub = subs.add_parser("setup", help="Configura e-mail e senha; assinatura opcional depois.")
    sub.add_argument("--provider", choices=("icloud","kinghost"))
    sub.add_argument("--email", help="E-mail de login; se omitido, será solicitado.")
    sub.add_argument("--sender-name")
    sub.add_argument("--replace-account", action="store_true", help="Troca a conta ativa preservando o histórico e a fila anterior.")
    sub.add_argument("--sender", help="Remetente autorizado opcional; padrão: e-mail informado.")
    sub.add_argument("--json", action="store_true")
    sub.add_argument("--data-dir", default=argparse.SUPPRESS)
    sub = subs.add_parser("signature", help="Configura ou remove assinatura para futuras importações.")
    group = sub.add_mutually_exclusive_group(required=True)
    group.add_argument("--html")
    group.add_argument("--clear", action="store_true")
    sub.add_argument("--text")
    sub.add_argument("--json", action="store_true")
    sub.add_argument("--data-dir", default=argparse.SUPPRESS)
    for name in ("doctor","run","resume"):
        sub = subs.add_parser(name, help="Diagnostica sem enviar." if name == "doctor" else "Executa envio SMTP explicitamente autorizado pela operação CLI.")
        sub.add_argument("--json", action="store_true")
        sub.add_argument("--data-dir", default=argparse.SUPPRESS)
        if name == "run":
            sub.add_argument("--batch", required=True)
            sub.add_argument("--limit", type=int, required=True)
            sub.add_argument("--request-id", required=True)
            sub.add_argument("--max-attempts", type=int, default=100)
            sub.add_argument("--max-seconds", type=int, default=3600)
        if name == "resume":
            sub.add_argument("--run", required=True)
    sub = subs.add_parser("test", help="Envia uma única cópia ao destinatário explícito.")
    sub.add_argument("id")
    sub.add_argument("--to", required=True)
    sub.add_argument("--request-id", required=True)
    sub.add_argument("--json", action="store_true")
    sub.add_argument("--data-dir", default=argparse.SUPPRESS)
    return p


def dispatch(args):
    directory = data_path(args.data_dir)
    if args.command == 'archive':
        from .archiving import configure, archive_status, retry_archive
        if args.action in ('configure','check','disable'):
            if args.id is not None:
                raise QueueError('INVALID_ARGUMENT', 'Esta ação não aceita ID.')
            return configure(directory,args.action,args.folder,args.create)
        if not args.id or args.folder is not None or args.create:
            raise QueueError('INVALID_ARGUMENT', 'status/retry exigem somente ID.')
        from .storage import Store
        from .config import load_config
        from .worker import worker_lock
        store = Store(directory)
        try:
            if args.action == 'status':
                return archive_status(store,args.id)
            with worker_lock(directory):
                result = retry_archive(store,load_config(directory),args.id)
            if result['state'] != 'archived':
                raise QueueError('ARCHIVE_ATTENTION', 'Arquivo requer atenção; o envio SMTP continua registrado.', 5, details=result)
            return result
        finally:
            store.close()
    if args.command == 'dkim':
        from .dkim_signing import configure
        return configure(directory,args.action)
    if args.command == "sender":
        from .setup import configure_sender
        return configure_sender(directory, args.email, args.name)
    if args.command == "setup":
        from .setup import setup
        return setup(directory, sender=args.sender, provider=args.provider, email=args.email, sender_name=args.sender_name, replace_account=args.replace_account)
    if args.command == "signature":
        from .setup import configure_signature
        return configure_signature(directory, args.html, args.text, args.clear)
    if args.command in ("backup", "import", "validate", "list", "show", "cancel", "export", "preview", "status", "pause", "resolve", "doctor", "run", "resume", "test"):
        from .storage import Store
        store = Store(directory)
        try:
            if args.command in ("doctor","run","resume","test"):
                from .config import load_config
                from .transport import SMTPTransport, doctor
                from .worker import Worker
                config=load_config(directory)
                if args.command == "doctor": return doctor(store,config)
                if args.command == "test":
                    from .testing import send_test
                    result=send_test(store,config,SMTPTransport(config),args.id,args.to,args.request_id)
                    if result['message']['state']!='sent':
                        raise run_error(result['run'],result,'TEST_ATTENTION')
                    return result
                worker=Worker(store,SMTPTransport(config),config)
                result=worker.run(args.request_id,args.batch,args.limit,args.max_attempts,args.max_seconds) if args.command=="run" else worker.resume(args.run)
                if result['state']=='blocked' or result['counts']['failed'] or result['outcomes'].get('permanent') or result['outcomes'].get('uncertain'):
                    raise run_error(result)
                return result
            if args.command == "backup":
                return store.backup(args.output)
            if args.command == "resolve":
                from .resolution import resolve
                return resolve(store,args.id,args.action,args.reason,args.request_id)
            if args.command == "pause":
                from .worker import pause
                return pause(store,args.run)
            if args.command == "status":
                from .worker import status
                return status(store,args.run)
            if args.command == "preview":
                from .preview import preview
                return preview(store,args.id,args.format,args.output)
            from .queries import list_messages, show, cancel, export_batch
            if args.command == "list":
                return list_messages(store,args.batch,args.state,args.limit,args.cursor)
            if args.command == "show":
                return show(store,args.id,args.include_body)
            if args.command == "cancel":
                return cancel(store,args.id)
            if args.command == "export":
                return export_batch(store,args.batch,args.output)
            from .config import load_config
            from .importer import import_batch
            return import_batch(store, load_config(directory), args.file, args.batch, args.command == "validate")
        finally:
            store.close()
    raise QueueError("INVALID_ARGUMENT", "Nenhuma operação disponível nesta etapa.")


def run_error(run,details=None,code='RUN_ATTENTION'):
    reason=run.get('blocked_reason')
    config_codes={'AUTH_FAILED','TLS_INVALID','TLS_REQUIRED','SENDER_REFUSED','KEYCHAIN_DENIED','KEYCHAIN_UNAVAILABLE','CREDENTIAL_MISSING'}
    return QueueError(reason if reason in config_codes else code,'Execução requer atenção; consulte status.',4 if reason in config_codes else 5,details=run if details is None else details)


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        data = dispatch(args)
        result, code = dict(schema_version=1, ok=True, data=data), 0
    except QueueError as exc:
        result, code = dict(schema_version=1, ok=False, error=exc.as_dict()), exc.exit_code
    except (EOFError, KeyboardInterrupt):
        result, code = dict(schema_version=1, ok=False, error=dict(code="INPUT_CANCELLED", message="Entrada cancelada.", retryable=False)), 2
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        result, code = dict(schema_version=1, ok=False, error=dict(code="LOCAL_ERROR", message="Falha local; verifique arquivos e permissões.", retryable=False)), 4
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
