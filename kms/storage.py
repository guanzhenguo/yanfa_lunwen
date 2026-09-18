from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Protocol

from kms.config import Settings


def object_key(sha256: str, ext: str = 'pdf') -> str:
    digest = sha256.lower()
    return f'{digest[:2]}/{digest}.{ext.lstrip(".")}'


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class ObjectStore(Protocol):
    backend: str
    bucket: str

    def exists(self, key: str) -> bool: ...
    def put_file(self, key: str, path: Path, content_type: str = 'application/pdf') -> str: ...
    def get_bytes(self, key: str) -> bytes: ...
    def location(self, key: str) -> str: ...


class LocalStore:
    """用本地目录模拟 MinIO：{root}/{bucket}/{key}。"""

    backend = 'local'

    def __init__(self, root: Path, bucket: str = 'papers') -> None:
        self.root = Path(root)
        self.bucket = bucket
        (self.root / self.bucket).mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / self.bucket / key.replace('\\', '/').lstrip('/')

    def exists(self, key: str) -> bool:
        path = self._path(key)
        return path.is_file() and path.stat().st_size > 0

    def put_file(self, key: str, path: Path, content_type: str = 'application/pdf') -> str:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = Path(path).resolve()
        if dest.resolve() != src:
            shutil.copy2(src, dest)
        return str(dest)

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(f'本地对象不存在: {path}')
        return path.read_bytes()

    def location(self, key: str) -> str:
        return str(self._path(key))


class MinioStore:
    """真实 MinIO。未配置时不要实例化。"""

    backend = 'minio'

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = 'papers',
        secure: bool = False,
    ) -> None:
        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError('使用 MinIO 前请先安装：pip install minio') from exc

        if not endpoint or not access_key or not secret_key:
            raise ValueError('MinIO 需要 KMS_MINIO_ENDPOINT / ACCESS_KEY / SECRET_KEY')

        self.bucket = bucket
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def exists(self, key: str) -> bool:
        from minio.error import S3Error

        try:
            info = self._client.stat_object(self.bucket, key)
            return bool(info and (info.size or 0) > 0)
        except S3Error:
            return False

    def put_file(self, key: str, path: Path, content_type: str = 'application/pdf') -> str:
        self._client.fput_object(
            self.bucket,
            key,
            str(path),
            content_type=content_type,
        )
        return self.location(key)

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def location(self, key: str) -> str:
        return f'minio://{self.bucket}/{key}'


def create_store(settings: Settings) -> ObjectStore:
    if settings.uses_minio:
        return MinioStore(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )
    return LocalStore(root=settings.local_root, bucket=settings.minio_bucket)
