import json
import math
from pathlib import Path
from .errors import QueueError

DEFAULT_DIR = Path.home() / "Library/Application Support/SendMail"


def data_path(value=None):
    path = (Path(value).expanduser() if value else DEFAULT_DIR).resolve()
    forbidden = ("Mobile Documents", "CloudStorage", "Dropbox", "OneDrive", "Google Drive")
    roots=set()
    for origin in (Path.cwd().resolve(),Path(__file__).resolve().parent):
        for candidate in (origin,*origin.parents):
            if (candidate/'AGENTS.md').is_file() and (candidate/'pyproject.toml').is_file():
                roots.add(candidate)
    if any(path==root or root in path.parents for root in roots) or any(part.startswith(forbidden) for part in path.parts):
        raise QueueError("UNSAFE_DATA_DIR", "Use um diretório local fora do projeto e de pastas sincronizadas.")
    return path


def prepare_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def load_config(path):
    try:
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise QueueError("CONFIG_MISSING", "Configure a conta com setup antes desta operação.", 4)
    except (ValueError, OSError):
        raise QueueError("CONFIG_INVALID", "Não foi possível ler a configuração local.", 4)
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise QueueError("CONFIG_INVALID", "Versão de configuração inválida.", 4)
    required={'schema_version','account_id','login','sender','signature_html','signature_text'}
    allowed=required|{'interval_seconds','daily_budget','sender_name','interval_min_seconds','interval_max_seconds','provider','dkim','archive'}
    if not required<=config.keys() or config.keys()-allowed or any(not isinstance(config[k],str) or not config[k].strip() for k in required-{'schema_version'}):
        raise QueueError('CONFIG_INVALID','Campos da configuração inválidos ou desconhecidos.',4)
    smtp_settings(config)
    from .archiving import validate_settings
    validate_settings(config)
    if 'dkim' in config:
        from .dkim_signing import validate
        validate(config['dkim'])
    from .composer import address, header
    try:
        if "sender_name" in config:
            config["sender_name"]=header(config["sender_name"],"sender_name").strip()
        config['sender']=address(config['sender']); config['login']=address(config['login'])
        minimum=config.get('interval_min_seconds',config.get('interval_seconds',15))
        maximum=config.get('interval_max_seconds',max(45,minimum+30) if isinstance(minimum,(int,float)) else 45)
        if any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in (minimum,maximum)) or not 15<=minimum<maximum<=86400:
            raise ValueError()
        for field in ('signature_html','signature_text'):
            if not Path(config[field]).is_absolute(): raise ValueError()
    except (QueueError,ValueError):
        raise QueueError('CONFIG_INVALID','Endereços, assinaturas ou limites da configuração inválidos.',4)
    return config


SMTP_PROVIDERS = {
    'icloud': ('smtp.mail.me.com', 587, 'starttls'),
    'kinghost': ('smtp.kinghost.net', 465, 'ssl'),
}


def smtp_settings(config):
    provider=config.get('provider','icloud')
    if not isinstance(provider,str) or provider not in SMTP_PROVIDERS:
        raise QueueError('CONFIG_INVALID','Provedor SMTP inválido.',4)
    return SMTP_PROVIDERS[provider]
