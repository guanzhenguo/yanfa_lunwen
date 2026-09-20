from __future__ import annotations

import re
from typing import Any, Iterable

from kms.catalog import _now

KEYWORD_SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    extract_prompt TEXT NOT NULL DEFAULT '',
    extract_schema TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS document_keywords (
    document_id INTEGER NOT NULL,
    keyword_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    PRIMARY KEY (document_id, keyword_id)
);

CREATE INDEX IF NOT EXISTS idx_doc_keywords_kw
    ON document_keywords(keyword_id);
"""


def normalize_name(name: str) -> str:
    return re.sub(r'\s+', ' ', (name or '').strip())


def slugify(name: str) -> str:
    text = normalize_name(name).lower()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^a-z0-9\-\u4e00-\u9fff]+', '', text)
    return text[:80]


def parse_keyword_names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = [str(item) for item in value]
    else:
        raw = re.split(r'[,;\n/|，、]+', str(value))
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = normalize_name(item)
        slug = slugify(name)
        if not name or not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(name)
        if len(out) >= 20:
            break
    return out


def public_keyword(row: dict[str, Any], *, include_prompt: bool = True) -> dict[str, Any]:
    prompt = row.get('extract_prompt') or ''
    schema = row.get('extract_schema') or ''
    payload = {
        'id': row['id'],
        'name': row.get('name') or '',
        'slug': row.get('slug') or '',
        'paper_count': int(row.get('paper_count') or 0),
        'has_custom_prompt': bool(prompt.strip()),
        'has_custom_schema': bool(schema.strip()),
        'updated_at': row.get('updated_at') or '',
        'updated_by': row.get('updated_by') or '',
    }
    if include_prompt:
        payload['extract_prompt'] = prompt
        payload['extract_schema'] = schema
    return payload


class KeywordStore:
    def __init__(self, catalog) -> None:
        self.conn = catalog.conn
        self.conn.executescript(KEYWORD_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        cols = {row[1] for row in self.conn.execute('PRAGMA table_info(keywords)')}
        if 'extract_schema' not in cols:
            self.conn.execute(
                "ALTER TABLE keywords ADD COLUMN extract_schema TEXT NOT NULL DEFAULT ''"
            )

    def get(self, keyword_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            'SELECT * FROM keywords WHERE id = ?',
            (keyword_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_by_slug(self, slug: str) -> dict[str, Any] | None:
        if not slug:
            return None
        row = self.conn.execute(
            'SELECT * FROM keywords WHERE slug = ?',
            (slug,),
        ).fetchone()
        return dict(row) if row else None

    def get_or_create(self, name: str, *, updated_by: str = '') -> dict[str, Any]:
        name = normalize_name(name)
        slug = slugify(name)
        if not slug:
            raise ValueError('empty keyword')
        existing = self.get_by_slug(slug)
        if existing:
            return existing
        now = _now()
        cursor = self.conn.execute(
            """
            INSERT INTO keywords (name, slug, extract_prompt, created_at, updated_at, updated_by)
            VALUES (?, ?, '', ?, ?, ?)
            """,
            (name, slug, now, now, updated_by),
        )
        self.conn.commit()
        return self.get(int(cursor.lastrowid)) or {'id': int(cursor.lastrowid), 'name': name, 'slug': slug}

    def list_keywords(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT k.*, COUNT(dk.document_id) AS paper_count
            FROM keywords k
            LEFT JOIN document_keywords dk ON dk.keyword_id = k.id
            GROUP BY k.id
            ORDER BY paper_count DESC, k.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def update_keyword(
        self,
        keyword_id: int,
        *,
        name: str | None = None,
        extract_prompt: str | None = None,
        extract_schema: str | None = None,
        updated_by: str = '',
    ) -> dict[str, Any]:
        current = self.get(keyword_id)
        if not current:
            raise ValueError('keyword not found')
        new_name = current['name']
        new_slug = current['slug']
        if name is not None:
            new_name = normalize_name(name)
            new_slug = slugify(new_name)
            if not new_slug:
                raise ValueError('empty keyword')
            clash = self.get_by_slug(new_slug)
            if clash and clash['id'] != keyword_id:
                raise ValueError('keyword already exists')
        prompt = current.get('extract_prompt') or ''
        if extract_prompt is not None:
            prompt = extract_prompt
        schema = current.get('extract_schema') or ''
        if extract_schema is not None:
            schema = extract_schema
        self.conn.execute(
            """
            UPDATE keywords
            SET name = ?, slug = ?, extract_prompt = ?, extract_schema = ?,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (new_name, new_slug, prompt, schema, _now(), updated_by, keyword_id),
        )
        self.conn.commit()
        return self.get(keyword_id) or current

    def delete_keyword(self, keyword_id: int) -> None:
        self.conn.execute(
            'DELETE FROM document_keywords WHERE keyword_id = ?',
            (keyword_id,),
        )
        self.conn.execute('DELETE FROM keywords WHERE id = ?', (keyword_id,))
        self.conn.commit()

    def keywords_for(self, document_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT k.*, dk.source
            FROM document_keywords dk
            JOIN keywords k ON k.id = dk.keyword_id
            WHERE dk.document_id = ?
            ORDER BY k.name COLLATE NOCASE
            """,
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def keywords_for_many(self, document_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]:
        ids = [int(item) for item in document_ids]
        if not ids:
            return {}
        placeholders = ','.join('?' for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT dk.document_id, k.*, dk.source
            FROM document_keywords dk
            JOIN keywords k ON k.id = dk.keyword_id
            WHERE dk.document_id IN ({placeholders})
            ORDER BY k.name COLLATE NOCASE
            """,
            ids,
        ).fetchall()
        mapping: dict[int, list[dict[str, Any]]] = {doc_id: [] for doc_id in ids}
        for row in rows:
            item = dict(row)
            mapping.setdefault(item['document_id'], []).append(item)
        return mapping

    def set_document_keywords(
        self,
        document_id: int,
        names: list[str],
        *,
        source: str = 'manual',
        updated_by: str = '',
    ) -> list[dict[str, Any]]:
        clean = parse_keyword_names(names)
        self.conn.execute(
            'DELETE FROM document_keywords WHERE document_id = ?',
            (document_id,),
        )
        for name in clean:
            keyword = self.get_or_create(name, updated_by=updated_by)
            self.conn.execute(
                """
                INSERT OR IGNORE INTO document_keywords (document_id, keyword_id, source)
                VALUES (?, ?, ?)
                """,
                (document_id, keyword['id'], source),
            )
        self.conn.commit()
        return self.keywords_for(document_id)

    def add_document_keywords(
        self,
        document_id: int,
        names: list[str],
        *,
        source: str = 'ingest',
        updated_by: str = '',
    ) -> list[dict[str, Any]]:
        for name in parse_keyword_names(names):
            keyword = self.get_or_create(name, updated_by=updated_by)
            self.conn.execute(
                """
                INSERT OR IGNORE INTO document_keywords (document_id, keyword_id, source)
                VALUES (?, ?, ?)
                """,
                (document_id, keyword['id'], source),
            )
        self.conn.commit()
        return self.keywords_for(document_id)
