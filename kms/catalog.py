from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')


def year_from_published(published: str) -> int | None:
    matches = _YEAR_RE.findall(published or '')
    if not matches:
        return None
    return int(matches[-1])


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    doi TEXT,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT '',
    authors TEXT NOT NULL DEFAULT '',
    published TEXT NOT NULL DEFAULT '',
    parent TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    open_access INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'springer',
    pdf_url TEXT NOT NULL DEFAULT '',
    storage_key TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    file_location TEXT NOT NULL DEFAULT '',
    year INTEGER,
    uploaded_by TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(url)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_doi
    ON documents(doi) WHERE doi IS NOT NULL AND doi != '';

CREATE INDEX IF NOT EXISTS idx_documents_sha256
    ON documents(sha256) WHERE sha256 != '';

CREATE TABLE IF NOT EXISTS ingest_jobs (
    id INTEGER PRIMARY KEY,
    query TEXT NOT NULL,
    page_start INTEGER NOT NULL DEFAULT 1,
    pages INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    downloaded_count INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT ''
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Catalog:
    def __init__(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.conn.executescript(SCHEMA)
        from kms.keywords import KEYWORD_SCHEMA

        self.conn.executescript(KEYWORD_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        cols = {row[1] for row in self.conn.execute('PRAGMA table_info(documents)')}
        if 'year' not in cols:
            self.conn.execute('ALTER TABLE documents ADD COLUMN year INTEGER')
        if 'uploaded_by' not in cols:
            self.conn.execute(
                "ALTER TABLE documents ADD COLUMN uploaded_by TEXT NOT NULL DEFAULT ''"
            )
        if 'original_filename' not in cols:
            self.conn.execute(
                "ALTER TABLE documents ADD COLUMN original_filename TEXT NOT NULL DEFAULT ''"
            )
        missing = self.conn.execute(
            'SELECT id, published FROM documents WHERE year IS NULL OR year = 0'
        ).fetchall()
        for row in missing:
            year = year_from_published(row['published'])
            if year:
                self.conn.execute(
                    'UPDATE documents SET year = ? WHERE id = ?',
                    (year, row['id']),
                )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> 'Catalog':
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        if not doi:
            return None
        row = self.conn.execute(
            'SELECT * FROM documents WHERE doi = ?',
            (doi,),
        ).fetchone()
        return dict(row) if row else None

    def get_by_url(self, url: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            'SELECT * FROM documents WHERE url = ?',
            (url,),
        ).fetchone()
        return dict(row) if row else None

    def get_existing(self, doi: str, url: str) -> dict[str, Any] | None:
        return self.get_by_doi(doi) or self.get_by_url(url)

    def upsert_document(self, article: dict[str, Any]) -> int:
        doi = (article.get('doi') or '').strip()
        url = article['url']
        existing = self.get_existing(doi, url)
        now = _now()
        payload = {
            'doi': doi,
            'url': url,
            'title': article.get('title') or '',
            'content_type': article.get('content_type') or '',
            'authors': article.get('authors') or '',
            'published': article.get('published') or '',
            'parent': article.get('parent') or '',
            'description': article.get('description') or '',
            'open_access': 1 if article.get('open_access') else 0,
            'source': article.get('source') or 'springer',
            'pdf_url': article.get('pdf_url') or '',
            'storage_key': article.get('storage_key') or '',
            'sha256': article.get('sha256') or '',
            'file_location': article.get('file_location') or article.get('pdf_path') or '',
            'year': article.get('year') if article.get('year') not in (None, '') else year_from_published(article.get('published') or ''),
            'uploaded_by': article.get('uploaded_by') or '',
            'original_filename': article.get('original_filename') or '',
            'updated_at': now,
        }
        if existing:
            # 已入库的文件指针不被空值覆盖
            if not payload['storage_key']:
                payload['storage_key'] = existing['storage_key']
            if not payload['sha256']:
                payload['sha256'] = existing['sha256']
            if not payload['file_location']:
                payload['file_location'] = existing['file_location']
            if not payload['pdf_url']:
                payload['pdf_url'] = existing['pdf_url']
            if not payload['uploaded_by']:
                payload['uploaded_by'] = existing.get('uploaded_by') or ''
            if not payload['original_filename']:
                payload['original_filename'] = existing.get('original_filename') or ''
            self.conn.execute(
                """
                UPDATE documents SET
                    doi=:doi, url=:url, title=:title, content_type=:content_type,
                    authors=:authors, published=:published, parent=:parent,
                    description=:description, open_access=:open_access,
                    source=:source, pdf_url=:pdf_url, storage_key=:storage_key,
                    sha256=:sha256, file_location=:file_location, year=:year,
                    uploaded_by=:uploaded_by, original_filename=:original_filename,
                    updated_at=:updated_at
                WHERE id=:id
                """,
                {**payload, 'id': existing['id']},
            )
            self.conn.commit()
            return int(existing['id'])

        payload['created_at'] = now
        cursor = self.conn.execute(
            """
            INSERT INTO documents (
                doi, url, title, content_type, authors, published, parent,
                description, open_access, source, pdf_url, storage_key,
                sha256, file_location, year, uploaded_by, original_filename,
                created_at, updated_at
            ) VALUES (
                :doi, :url, :title, :content_type, :authors, :published, :parent,
                :description, :open_access, :source, :pdf_url, :storage_key,
                :sha256, :file_location, :year, :uploaded_by, :original_filename,
                :created_at, :updated_at
            )
            """,
            payload,
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def start_job(self, query: str, page_start: int, pages: int) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO ingest_jobs (query, page_start, pages, status, started_at)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (query, page_start, pages, _now()),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def finish_job(
        self,
        job_id: int,
        *,
        status: str,
        item_count: int,
        downloaded_count: int,
        error: str = '',
    ) -> None:
        self.conn.execute(
            """
            UPDATE ingest_jobs
            SET status=?, item_count=?, downloaded_count=?, error=?, finished_at=?
            WHERE id=?
            """,
            (status, item_count, downloaded_count, error, _now(), job_id),
        )
        self.conn.commit()

    def get_by_id(self, doc_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            'SELECT * FROM documents WHERE id = ?',
            (doc_id,),
        ).fetchone()
        return dict(row) if row else None

    def stats(self) -> dict[str, int]:
        total = self.conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
        oa = self.conn.execute(
            'SELECT COUNT(*) FROM documents WHERE open_access = 1'
        ).fetchone()[0]
        with_pdf = self.conn.execute(
            "SELECT COUNT(*) FROM documents WHERE storage_key != ''"
        ).fetchone()[0]
        return {
            'total': int(total),
            'oa': int(oa),
            'with_pdf': int(with_pdf),
        }

    def search(
        self,
        *,
        q: str = '',
        doi: str = '',
        year_from: int | None = None,
        year_to: int | None = None,
        oa: bool | None = None,
        has_pdf: bool | None = None,
        keyword: str = '',
        keyword_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []

        text = (q or '').strip()
        if text:
            where.append(
                '(title LIKE ? OR authors LIKE ? OR description LIKE ? '
                'OR doi LIKE ? OR parent LIKE ? OR id IN ('
                'SELECT document_id FROM document_keywords dk '
                'JOIN keywords k ON k.id = dk.keyword_id '
                'WHERE k.name LIKE ? OR k.slug LIKE ?))'
            )
            like = f'%{text}%'
            params.extend([like, like, like, like, like, like, like])

        doi_q = (doi or '').strip()
        if doi_q:
            where.append('doi LIKE ?')
            params.append(f'%{doi_q}%')

        if year_from:
            where.append('year >= ?')
            params.append(int(year_from))
        if year_to:
            where.append('year <= ?')
            params.append(int(year_to))

        if oa is True:
            where.append('open_access = 1')
        elif oa is False:
            where.append('open_access = 0')

        if has_pdf is True:
            where.append("storage_key != ''")
        elif has_pdf is False:
            where.append("(storage_key IS NULL OR storage_key = '')")

        topic = (keyword or '').strip()
        if keyword_id:
            where.append(
                'id IN (SELECT document_id FROM document_keywords WHERE keyword_id = ?)'
            )
            params.append(int(keyword_id))
        elif topic:
            where.append(
                'id IN (SELECT document_id FROM document_keywords dk '
                'JOIN keywords k ON k.id = dk.keyword_id '
                'WHERE k.slug = ? OR k.name LIKE ?)'
            )
            params.extend([topic.lower(), f'%{topic}%'])

        sql = 'SELECT * FROM documents'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY COALESCE(year, 0) DESC, id DESC LIMIT ? OFFSET ?'
        params.extend([int(limit), int(offset)])
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def public_document(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': row['id'],
        'doi': row.get('doi') or '',
        'url': row.get('url') or '',
        'title': row.get('title') or '',
        'content_type': row.get('content_type') or '',
        'authors': row.get('authors') or '',
        'published': row.get('published') or '',
        'parent': row.get('parent') or '',
        'description': row.get('description') or '',
        'open_access': bool(row.get('open_access')),
        'source': row.get('source') or 'springer',
        'year': row.get('year'),
        'has_pdf': bool(row.get('storage_key')),
        'storage_key': row.get('storage_key') or '',
        'uploaded_by': row.get('uploaded_by') or '',
        'original_filename': row.get('original_filename') or '',
        'institution': row.get('parent') or '',
        'created_at': row.get('created_at') or '',
        'keywords': list(row.get('keywords') or []),
    }
