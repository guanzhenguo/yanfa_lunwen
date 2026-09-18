from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / 'config.toml'


def _env(name: str, default: str = '') -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == '' else value.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


def _toml_str(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _section(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    return data


@dataclass(frozen=True)
class Settings:
    storage_backend: str
    local_root: Path
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    catalog_path: Path
    ai_base_url: str
    ai_api_key: str
    ai_model: str
    ai_timeout_seconds: int
    neo4j_enabled: bool
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str

    @property
    def uses_minio(self) -> bool:
        return self.storage_backend == 'minio'

    @property
    def ai_ready(self) -> bool:
        return bool(self.ai_base_url and self.ai_api_key and self.ai_model)


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    import tomllib

    with path.open('rb') as fh:
        return tomllib.load(fh)


def load_settings(
    storage_root: str | None = None,
    catalog_path: str | None = None,
    config_path: Path | None = None,
) -> Settings:
    raw = _load_toml(config_path or CONFIG_PATH)
    storage = _section(raw.get('storage') or {})
    ai = _section(raw.get('ai') or {})
    neo4j = _section(raw.get('neo4j') or {})

    backend = _env('KMS_STORAGE', str(storage.get('backend') or 'local')).lower()
    if backend not in {'local', 'minio'}:
        raise ValueError(f'KMS_STORAGE must be local or minio, got {backend}')

    local_root = Path(
        storage_root
        or _env('KMS_LOCAL_ROOT', str(storage.get('local_root') or PROJECT_ROOT / 'data' / 'minio'))
    )
    catalog = Path(
        catalog_path
        or _env('KMS_CATALOG', str(storage.get('catalog') or PROJECT_ROOT / 'data' / 'catalog.sqlite'))
    )
    if not local_root.is_absolute():
        local_root = (PROJECT_ROOT / local_root).resolve()
    if not catalog.is_absolute():
        catalog = (PROJECT_ROOT / catalog).resolve()

    return Settings(
        storage_backend=backend,
        local_root=local_root,
        minio_endpoint=_env('KMS_MINIO_ENDPOINT', str(storage.get('minio_endpoint') or '')),
        minio_access_key=_env('KMS_MINIO_ACCESS_KEY', str(storage.get('minio_access_key') or '')),
        minio_secret_key=_env('KMS_MINIO_SECRET_KEY', str(storage.get('minio_secret_key') or '')),
        minio_bucket=_env('KMS_MINIO_BUCKET', str(storage.get('minio_bucket') or 'papers')),
        minio_secure=_env_bool('KMS_MINIO_SECURE', bool(storage.get('minio_secure') or False)),
        catalog_path=catalog,
        ai_base_url=_env('KMS_AI_BASE_URL', str(ai.get('base_url') or 'https://api.openai.com/v1')),
        ai_api_key=_env('KMS_AI_API_KEY', str(ai.get('api_key') or '')),
        ai_model=_env('KMS_AI_MODEL', str(ai.get('model') or 'gpt-4o-mini')),
        ai_timeout_seconds=int(_env('KMS_AI_TIMEOUT', str(ai.get('timeout_seconds') or 90))),
        neo4j_enabled=_env_bool('KMS_NEO4J_ENABLED', bool(neo4j.get('enabled') or False)),
        neo4j_uri=_env('KMS_NEO4J_URI', str(neo4j.get('uri') or 'bolt://127.0.0.1:7687')),
        neo4j_user=_env('KMS_NEO4J_USER', str(neo4j.get('user') or 'neo4j')),
        neo4j_password=_env('KMS_NEO4J_PASSWORD', str(neo4j.get('password') or '')),
        neo4j_database=_env('KMS_NEO4J_DATABASE', str(neo4j.get('database') or 'neo4j')),
    )


def public_ai_settings(settings: Settings) -> dict:
    return {
        'base_url': settings.ai_base_url,
        'model': settings.ai_model,
        'timeout_seconds': settings.ai_timeout_seconds,
        'api_key': settings.ai_api_key,
        'api_key_set': bool(settings.ai_api_key),
        'ready': settings.ai_ready,
    }


def public_neo4j_settings(settings: Settings) -> dict:
    return {
        'enabled': settings.neo4j_enabled,
        'uri': settings.neo4j_uri,
        'user': settings.neo4j_user,
        'password': settings.neo4j_password,
        'database': settings.neo4j_database,
    }


def save_config(settings: Settings, path: Path | None = None) -> None:
    target = path or CONFIG_PATH
    text = f'''# PV lab knowledge library
# Fill [ai] before using parse/extract. Fill [neo4j] later for graph sync.

[storage]
backend = {_toml_str(settings.storage_backend)}
local_root = {_toml_str(_rel_or_abs(settings.local_root))}
catalog = {_toml_str(_rel_or_abs(settings.catalog_path))}
minio_endpoint = {_toml_str(settings.minio_endpoint)}
minio_access_key = {_toml_str(settings.minio_access_key)}
minio_secret_key = {_toml_str(settings.minio_secret_key)}
minio_bucket = {_toml_str(settings.minio_bucket)}
minio_secure = {str(settings.minio_secure).lower()}

[ai]
base_url = {_toml_str(settings.ai_base_url)}
api_key = {_toml_str(settings.ai_api_key)}
model = {_toml_str(settings.ai_model)}
timeout_seconds = {int(settings.ai_timeout_seconds)}

[neo4j]
enabled = {str(settings.neo4j_enabled).lower()}
uri = {_toml_str(settings.neo4j_uri)}
user = {_toml_str(settings.neo4j_user)}
password = {_toml_str(settings.neo4j_password)}
database = {_toml_str(settings.neo4j_database)}
'''
    target.write_text(text, encoding='utf-8')


def _rel_or_abs(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def update_ai_settings(payload: dict) -> Settings:
    current = load_settings()
    key = payload.get('api_key')
    if key is None:
        key = current.ai_api_key
    updated = replace(
        current,
        ai_base_url=str(payload.get('base_url') or current.ai_base_url).strip(),
        ai_api_key=str(key).strip(),
        ai_model=str(payload.get('model') or current.ai_model).strip(),
        ai_timeout_seconds=int(payload.get('timeout_seconds') or current.ai_timeout_seconds),
    )
    save_config(updated)
    return updated


def update_neo4j_settings(payload: dict) -> Settings:
    current = load_settings()
    password = payload.get('password')
    if password is None:
        password = current.neo4j_password
    updated = replace(
        current,
        neo4j_enabled=bool(payload.get('enabled', current.neo4j_enabled)),
        neo4j_uri=str(payload.get('uri') or current.neo4j_uri).strip(),
        neo4j_user=str(payload.get('user') or current.neo4j_user).strip(),
        neo4j_password=str(password).strip(),
        neo4j_database=str(payload.get('database') or current.neo4j_database).strip(),
    )
    save_config(updated)
    return updated
