from __future__ import annotations

import json
import re
from typing import Any

from kms.catalog import Catalog, _now
from kms.config import Settings
from kms.keywords import parse_keyword_names

PROMPT_METADATA = 'metadata_parse'
PROMPT_EXTRACT = 'knowledge_extract'
PROMPT_CHAT = 'knowledge_qa'
PROMPT_LOCALIZE = 'knowledge_localize'

DEFAULT_PROMPTS = {
    PROMPT_METADATA: (
        'You extract bibliographic metadata from a photovoltaic research PDF filename '
        'and optional user fields. Return JSON only with keys: '
        'title, authors, doi, year, description. Keep user-provided non-empty fields. '
        'If unknown, use an empty string. Year must be a 4-digit year or empty. '
        'Also return keywords as an array of 1 to 8 topical terms from the title/abstract. '
        'Keep user-provided keywords when present.'
    ),
    PROMPT_EXTRACT: (
        'Extract a knowledge graph from ONE chunk of a photovoltaic paper. '
        'Use only this chunk text plus the given bibliographic fields. '
        'Do not invent efficiencies, temperatures, materials, or process steps '
        'that do not appear in the chunk. Prefer Materials, Process, Metric, Concept, Keyword. '
        'Always keep the Paper node key paper:{id}. Return JSON only: '
        '{"nodes":[{"key","label","type","properties"}],'
        '"edges":[{"source","target","type","properties"}]}. '
        'Node types: Paper, Author, Institution, Keyword, Concept, Material, Process, Metric, File, Year. '
        'Use stable keys like paper:1, material:csfai, process:anneal, metric:pce. '
        'At most 20 nodes per chunk. Put a short evidence quote in properties.evidence.'
    ),
    PROMPT_CHAT: (
        '你是光伏实验室文献库的交互式问答助手。'
        '根据检索到的论文分块、关键词和图谱三元组回答用户问题，保持专业严谨，少用 emoji。'
        '只依据提供的上下文作答，不要编造实验数据。'
        '数值必须来自摘录或三元组；若上下文不足以回答，明确说明缺口，并列出最相关的论文。'
        '引用文献时使用 [1]、[2] 这种序号，对应检索结果中的文档编号。'
        '除非用户询问系统如何工作，否则不要解释检索实现细节。'
    ),
    PROMPT_LOCALIZE: (
        '将光伏论文知识图谱翻译成简体中文，供中文检索和展示。'
        '保持原有 node key、edge source/target 以及英文 type 不变，不要新增或删除节点和边。'
        '化学式、材料缩写、人名可保留原文，工艺、指标、概念、关系要译成中文。'
        '只返回 JSON：'
        '{"nodes":[{"key","label_zh","type_zh"}],'
        '"edges":[{"source","target","type","type_zh"}]}。'
        'type_zh 用：论文、作者、机构、关键词、概念、材料、工艺、指标、文件、年份。'
    ),
}

LEGACY_PROMPTS = {
    PROMPT_EXTRACT: (
        'Extract a knowledge graph from a photovoltaic paper record. '
        'Focus on keywords and title-related concepts: cell technology, process, '
        'materials, reliability metrics, institutions, and authors. '
        'Always keep file/system attributes. Return JSON: '
        '{"nodes":[{"key","label","type","properties"}],'
        '"edges":[{"source","target","type","properties"}]}. '
        'Node types: Paper, Author, Institution, Keyword, Concept, Material, Process, Metric, File, Year. '
        'Use stable keys like paper:1, author:name, keyword:topcon.'
    ),
    PROMPT_CHAT: (
        '你是光伏实验室文献库的交互式问答助手。'
        '根据检索到的论文回答用户问题，保持专业严谨，少用 emoji。'
        '只依据提供的文献题名、摘要、正文摘录、关键词和图谱三元组作答，不要编造实验数据。'
        '数值必须来自摘录或三元组；若文献不足以回答，明确说明缺口，并列出最相关的论文。'
        '引用文献时使用 [1]、[2] 这种序号，对应检索结果中的编号。'
        '除非用户询问系统如何工作，否则不要解释检索实现细节。'
    ),
}

KG_SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_prompts (
    name TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS kg_runs (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    prompt_name TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    zh_status TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    reviewed_by TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_kg_runs_doc ON kg_runs(document_id, id DESC);

CREATE TABLE IF NOT EXISTS kg_nodes (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    node_key TEXT NOT NULL,
    label TEXT NOT NULL,
    label_zh TEXT NOT NULL DEFAULT '',
    node_type TEXT NOT NULL,
    node_type_zh TEXT NOT NULL DEFAULT '',
    properties_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'ai',
    UNIQUE(run_id, node_key)
);

CREATE TABLE IF NOT EXISTS kg_edges (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    source_key TEXT NOT NULL,
    target_key TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    rel_type_zh TEXT NOT NULL DEFAULT '',
    properties_json TEXT NOT NULL DEFAULT '{}'
);
"""

_STOP = {
    'a', 'an', 'the', 'of', 'and', 'or', 'for', 'to', 'in', 'on', 'with', 'by',
    'from', 'using', 'based', 'via', 'into', 'at',
}

_HAN_RE = re.compile(r'[\u4e00-\u9fff]')

TYPE_ZH = {
    'Paper': '论文',
    'Author': '作者',
    'Institution': '机构',
    'Keyword': '关键词',
    'Concept': '概念',
    'Material': '材料',
    'Process': '工艺',
    'Metric': '指标',
    'File': '文件',
    'Year': '年份',
}

REL_ZH = {
    'HAS_KEYWORD': '具有关键词',
    'AUTHORED_BY': '作者为',
    'PUBLISHED_BY': '发表机构',
    'PUBLISHED_IN': '发表于',
    'HAS_FILE': '包含文件',
    'RELATED_TO': '相关',
    'USES': '使用',
    'USES_MATERIAL': '使用材料',
    'HAS_PROCESS': '包含工艺',
    'HAS_METRIC': '具有指标',
    'MEASURES': '测量',
    'CONTAINS': '包含',
    'IMPROVES': '提升',
    'FABRICATED_BY': '制备于',
    'ANNEALED_AT': '退火条件',
    'HAS_CONCEPT': '涉及概念',
    'MENTIONS': '提及',
    'HAS_AUTHOR': '作者为',
    'AFFILIATED_WITH': '所属机构',
    'REPORTS': '报道',
    'ACHIEVES': '达到',
    'ENABLES': '实现',
}

LABEL_ZH = {
    'perovskite': '钙钛矿',
    'perovskites': '钙钛矿',
    'tandem': '叠层',
    'tandem cell': '叠层电池',
    'solar cell': '太阳电池',
    'solar cells': '太阳电池',
    'silicon': '硅',
    'anneal': '退火',
    'annealing': '退火',
    'passivation': '钝化',
    'tunnel oxide': '隧穿氧化层',
    'contact resistivity': '接触电阻率',
    'efficiency': '效率',
    'power conversion efficiency': '光电转换效率',
    'pce': '光电转换效率',
    'fill factor': '填充因子',
    'open-circuit voltage': '开路电压',
    'short-circuit current': '短路电流',
    'reliability': '可靠性',
    'interface': '界面',
    'precursor': '前驱体',
    'film': '薄膜',
    'thin film': '薄膜',
    'crystallization': '结晶',
    'stability': '稳定性',
}


def looks_zh(text: str) -> bool:
    return bool(_HAN_RE.search(text or ''))


def translate_label(label: str) -> str:
    text = (label or '').strip()
    if not text or looks_zh(text):
        return text
    lowered = text.lower()
    if lowered in LABEL_ZH:
        return LABEL_ZH[lowered]
    phrases = sorted(LABEL_ZH.items(), key=lambda item: len(item[0]), reverse=True)
    out = lowered
    for src, dst in phrases:
        if src in out:
            out = out.replace(src, dst)
    if out != lowered:
        return out
    return text


def translate_rel(rel: str) -> str:
    text = (rel or '').strip()
    if not text or looks_zh(text):
        return text
    key = re.sub(r'[\s\-]+', '_', text).upper()
    if key in REL_ZH:
        return REL_ZH[key]
    return REL_ZH.get(text, text)


def graph_as_extract(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    nodes = []
    for node in payload.get('nodes') or []:
        key = str(node.get('key') or node.get('node_key') or '').strip()
        if not key:
            continue
        nodes.append({
            'key': key,
            'label': str(node.get('label') or key),
            'type': str(node.get('type') or node.get('node_type') or 'Concept'),
            'label_zh': str(node.get('label_zh') or ''),
            'type_zh': str(node.get('type_zh') or node.get('node_type_zh') or ''),
            'source': str(node.get('source') or 'ai'),
            'properties': node.get('properties') or {},
        })
    edges = []
    for edge in payload.get('edges') or []:
        src = str(edge.get('source') or edge.get('source_key') or '').strip()
        dst = str(edge.get('target') or edge.get('target_key') or '').strip()
        rel = str(edge.get('type') or edge.get('rel_type') or 'RELATED_TO').strip()
        if not src or not dst:
            continue
        edges.append({
            'source': src,
            'target': dst,
            'type': rel,
            'type_zh': str(edge.get('type_zh') or edge.get('rel_type_zh') or ''),
            'properties': edge.get('properties') or {},
        })
    return {'nodes': nodes, 'edges': edges}



class KnowledgeGraph:
    def __init__(self, catalog: Catalog) -> None:
        self.conn = catalog.conn
        self.conn.executescript(KG_SCHEMA)
        self._migrate()
        self._seed_prompts()
        self.conn.commit()

    def _migrate(self) -> None:
        node_cols = {row[1] for row in self.conn.execute('PRAGMA table_info(kg_nodes)')}
        if 'label_zh' not in node_cols:
            self.conn.execute(
                "ALTER TABLE kg_nodes ADD COLUMN label_zh TEXT NOT NULL DEFAULT ''"
            )
        if 'node_type_zh' not in node_cols:
            self.conn.execute(
                "ALTER TABLE kg_nodes ADD COLUMN node_type_zh TEXT NOT NULL DEFAULT ''"
            )
        edge_cols = {row[1] for row in self.conn.execute('PRAGMA table_info(kg_edges)')}
        if 'rel_type_zh' not in edge_cols:
            self.conn.execute(
                "ALTER TABLE kg_edges ADD COLUMN rel_type_zh TEXT NOT NULL DEFAULT ''"
            )
        run_cols = {row[1] for row in self.conn.execute('PRAGMA table_info(kg_runs)')}
        if 'zh_status' not in run_cols:
            self.conn.execute(
                "ALTER TABLE kg_runs ADD COLUMN zh_status TEXT NOT NULL DEFAULT ''"
            )

    def _seed_prompts(self) -> None:
        now = _now()
        for name, body in DEFAULT_PROMPTS.items():
            exists = self.conn.execute(
                'SELECT name, body FROM kg_prompts WHERE name = ?',
                (name,),
            ).fetchone()
            if not exists:
                self.conn.execute(
                    """
                    INSERT INTO kg_prompts (name, title, body, updated_at, updated_by)
                    VALUES (?, ?, ?, ?, 'system')
                    """,
                    (name, name, body, now),
                )
                continue
            legacy = LEGACY_PROMPTS.get(name)
            if legacy and (exists['body'] or '') == legacy:
                self.conn.execute(
                    """
                    UPDATE kg_prompts
                    SET body = ?, updated_at = ?, updated_by = 'system'
                    WHERE name = ?
                    """,
                    (body, now, name),
                )

    def list_prompts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            'SELECT name, title, body, updated_at, updated_by FROM kg_prompts ORDER BY name'
        ).fetchall()
        return [dict(row) for row in rows]

    def get_prompt(self, name: str) -> str:
        row = self.conn.execute(
            'SELECT body FROM kg_prompts WHERE name = ?',
            (name,),
        ).fetchone()
        if row:
            return row['body']
        return DEFAULT_PROMPTS.get(name, '')

    def save_prompt(self, name: str, body: str, updated_by: str) -> dict[str, Any]:
        if name not in DEFAULT_PROMPTS:
            raise ValueError('unknown prompt')
        body = (body or '').strip()
        if not body:
            raise ValueError('prompt is empty')
        self.conn.execute(
            """
            UPDATE kg_prompts
            SET body = ?, updated_at = ?, updated_by = ?
            WHERE name = ?
            """,
            (body, _now(), updated_by, name),
        )
        self.conn.commit()
        row = self.conn.execute(
            'SELECT name, title, body, updated_at, updated_by FROM kg_prompts WHERE name = ?',
            (name,),
        ).fetchone()
        return dict(row)

    def latest_run(self, document_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            'SELECT * FROM kg_runs WHERE document_id = ? ORDER BY id DESC LIMIT 1',
            (document_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        row = self.conn.execute('SELECT * FROM kg_runs WHERE id = ?', (run_id,)).fetchone()
        return dict(row) if row else None

    def graph_payload(self, run_id: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        if not run:
            return {}
        nodes = [
            dict(row)
            for row in self.conn.execute(
                'SELECT node_key, label, label_zh, node_type, node_type_zh, properties_json, source FROM kg_nodes WHERE run_id = ?',
                (run_id,),
            ).fetchall()
        ]
        edges = [
            dict(row)
            for row in self.conn.execute(
                'SELECT source_key, target_key, rel_type, rel_type_zh, properties_json FROM kg_edges WHERE run_id = ?',
                (run_id,),
            ).fetchall()
        ]
        for node in nodes:
            node['properties'] = json.loads(node.pop('properties_json') or '{}')
        for edge in edges:
            edge['properties'] = json.loads(edge.pop('properties_json') or '{}')
        return {
            'run': public_run(run),
            'nodes': nodes,
            'edges': edges,
            'triples': graph_triples(nodes, edges),
            'triples_zh': graph_triples(nodes, edges, zh=True),
            'neo4j': neo4j_documents(nodes, edges),
        }

    def latest_triples(self, document_id: int, limit: int = 8) -> list[str]:
        latest = self.latest_run(document_id)
        if not latest or latest.get('status') not in {'pending_review', 'approved'}:
            return []
        payload = self.graph_payload(latest['id'])
        triples = payload.get('triples_zh') or payload.get('triples') or []
        return triples[:limit]

    def create_run(
        self,
        document: dict[str, Any],
        *,
        created_by: str,
        model: str,
        graph: dict[str, Any],
        raw_json: str = '',
        error: str = '',
        prompt_name: str = '',
    ) -> int:
        graph = graph or {'nodes': [], 'edges': []}
        has_nodes = bool(graph.get('nodes'))
        status = 'pending_review' if has_nodes else 'error'
        cursor = self.conn.execute(
            """
            INSERT INTO kg_runs (
                document_id, status, prompt_name, model, raw_json, error,
                created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document['id'],
                status,
                prompt_name or PROMPT_EXTRACT,
                model,
                raw_json,
                error,
                created_by,
                _now(),
            ),
        )
        run_id = int(cursor.lastrowid)
        if has_nodes:
            self._insert_graph(run_id, document['id'], graph)
        self.conn.commit()
        return run_id

    def review_run(self, run_id: int, status: str, reviewed_by: str, note: str = '') -> dict[str, Any]:
        if status not in {'approved', 'rejected'}:
            raise ValueError('status must be approved or rejected')
        run = self.get_run(run_id)
        if not run:
            raise ValueError('run not found')
        if run['status'] not in {'pending_review', 'approved', 'rejected'}:
            raise ValueError('run cannot be reviewed')
        self.conn.execute(
            """
            UPDATE kg_runs
            SET status = ?, reviewed_by = ?, reviewed_at = ?, review_note = ?
            WHERE id = ?
            """,
            (status, reviewed_by, _now(), note, run_id),
        )
        self.conn.commit()
        return self.get_run(run_id) or {}

    def graph_needs_zh(self, run_id: int) -> bool:
        missing_node = self.conn.execute(
            """
            SELECT 1 FROM kg_nodes
            WHERE run_id = ? AND (label_zh = '' OR node_type_zh = '')
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        missing_edge = self.conn.execute(
            """
            SELECT 1 FROM kg_edges
            WHERE run_id = ? AND rel_type_zh = ''
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        return bool(missing_node or missing_edge)

    def save_graph_zh(self, run_id: int, graph: dict[str, Any], status: str = '') -> None:
        for node in graph.get('nodes') or []:
            key = str(node.get('key') or node.get('node_key') or '').strip()
            if not key:
                continue
            self.conn.execute(
                """
                UPDATE kg_nodes
                SET label_zh = ?, node_type_zh = ?
                WHERE run_id = ? AND node_key = ?
                """,
                (
                    str(node.get('label_zh') or ''),
                    str(node.get('type_zh') or node.get('node_type_zh') or ''),
                    run_id,
                    key,
                ),
            )
        for edge in graph.get('edges') or []:
            src = str(edge.get('source') or edge.get('source_key') or '').strip()
            dst = str(edge.get('target') or edge.get('target_key') or '').strip()
            rel = str(edge.get('type') or edge.get('rel_type') or '').strip()
            if not src or not dst or not rel:
                continue
            self.conn.execute(
                """
                UPDATE kg_edges
                SET rel_type_zh = ?
                WHERE run_id = ? AND source_key = ? AND target_key = ? AND rel_type = ?
                """,
                (
                    str(edge.get('type_zh') or edge.get('rel_type_zh') or ''),
                    run_id,
                    src,
                    dst,
                    rel,
                ),
            )
        if status:
            self.conn.execute(
                'UPDATE kg_runs SET zh_status = ? WHERE id = ?',
                (status, run_id),
            )
        self.conn.commit()

    def _insert_graph(self, run_id: int, document_id: int, graph: dict[str, Any]) -> None:
        seen: set[str] = set()
        for node in graph.get('nodes') or []:
            key = str(node.get('key') or '').strip()
            if not key or key in seen:
                continue
            seen.add(key)
            self.conn.execute(
                """
                INSERT INTO kg_nodes (
                    run_id, document_id, node_key, label, label_zh, node_type, node_type_zh,
                    properties_json, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    document_id,
                    key,
                    str(node.get('label') or key),
                    str(node.get('label_zh') or ''),
                    str(node.get('type') or node.get('node_type') or 'Concept'),
                    str(node.get('type_zh') or node.get('node_type_zh') or ''),
                    json.dumps(node.get('properties') or {}, ensure_ascii=False),
                    str(node.get('source') or 'ai'),
                ),
            )
        for edge in graph.get('edges') or []:
            src = str(edge.get('source') or '').strip()
            dst = str(edge.get('target') or '').strip()
            rel = str(edge.get('type') or 'RELATED_TO').strip()
            if src not in seen or dst not in seen:
                continue
            self.conn.execute(
                """
                INSERT INTO kg_edges (
                    run_id, document_id, source_key, target_key, rel_type, rel_type_zh, properties_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    document_id,
                    src,
                    dst,
                    rel,
                    str(edge.get('type_zh') or edge.get('rel_type_zh') or ''),
                    json.dumps(edge.get('properties') or {}, ensure_ascii=False),
                ),
            )


def public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': run['id'],
        'document_id': run['document_id'],
        'status': run['status'],
        'model': run.get('model') or '',
        'prompt_name': run.get('prompt_name') or '',
        'error': run.get('error') or '',
        'created_by': run.get('created_by') or '',
        'created_at': run.get('created_at') or '',
        'reviewed_by': run.get('reviewed_by') or '',
        'reviewed_at': run.get('reviewed_at') or '',
        'review_note': run.get('review_note') or '',
        'zh_status': run.get('zh_status') or '',
        'neo4j_pending': run['status'] == 'approved',
    }


def graph_triples(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    limit: int = 10,
    *,
    zh: bool = False,
) -> list[str]:
    labels = {}
    for node in nodes:
        key = node.get('node_key') or node.get('key')
        if not key:
            continue
        if zh:
            labels[key] = node.get('label_zh') or node.get('label') or key
        else:
            labels[key] = node.get('label') or key
    skip_types = {'HAS_FILE', 'PUBLISHED_IN'}
    out: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        rel = edge.get('rel_type') or edge.get('type') or 'RELATED_TO'
        if rel in skip_types:
            continue
        if zh:
            rel = edge.get('rel_type_zh') or edge.get('type_zh') or translate_rel(rel)
        src = labels.get(edge.get('source_key') or edge.get('source') or '')
        dst = labels.get(edge.get('target_key') or edge.get('target') or '')
        if not src or not dst:
            continue
        item = f'{src} —{rel}→ {dst}'
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def neo4j_documents(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        'nodes': [
            {
                'id': node.get('node_key') or node.get('key'),
                'labels': [node.get('node_type') or node.get('type') or 'Concept'],
                'properties': {
                    'name': node.get('label') or '',
                    'source': node.get('source') or '',
                    **(node.get('properties') or {}),
                },
            }
            for node in nodes
        ],
        'relationships': [
            {
                'start': edge.get('source_key') or edge.get('source'),
                'end': edge.get('target_key') or edge.get('target'),
                'type': edge.get('rel_type') or edge.get('type') or 'RELATED_TO',
                'properties': edge.get('properties') or {},
            }
            for edge in edges
        ],
    }


def system_graph(document: dict[str, Any], extra_text: str = '') -> dict[str, Any]:
    paper_key = f"paper:{document['id']}"
    filename = document.get('original_filename') or document.get('title') or f"paper-{document['id']}"
    nodes = [
        {
            'key': paper_key,
            'label': document.get('title') or filename,
            'type': 'Paper',
            'source': 'system',
            'properties': {
                'title': document.get('title') or '',
                'doi': document.get('doi') or '',
                'year': document.get('year'),
                'abstract': document.get('description') or '',
                'source': document.get('source') or '',
                'filename': filename,
                'uploaded_by': document.get('uploaded_by') or '',
                'created_at': document.get('created_at') or '',
                'institution': document.get('parent') or '',
            },
        },
        {
            'key': f'file:{document["id"]}',
            'label': filename,
            'type': 'File',
            'source': 'system',
            'properties': {
                'filename': filename,
                'storage_key': document.get('storage_key') or '',
            },
        },
    ]
    edges = [
        {
            'source': paper_key,
            'target': f'file:{document["id"]}',
            'type': 'HAS_FILE',
            'properties': {},
        }
    ]
    if document.get('year'):
        year_key = f"year:{document['year']}"
        nodes.append({
            'key': year_key,
            'label': str(document['year']),
            'type': 'Year',
            'source': 'system',
            'properties': {'year': document['year']},
        })
        edges.append({'source': paper_key, 'target': year_key, 'type': 'PUBLISHED_IN', 'properties': {}})
    if document.get('parent'):
        inst_key = 'institution:' + _slug(document['parent'])
        nodes.append({
            'key': inst_key,
            'label': document['parent'],
            'type': 'Institution',
            'source': 'system',
            'properties': {'name': document['parent']},
        })
        edges.append({'source': paper_key, 'target': inst_key, 'type': 'PUBLISHED_BY', 'properties': {}})
    for author in _split_authors(document.get('authors') or ''):
        key = 'author:' + _slug(author)
        nodes.append({
            'key': key,
            'label': author,
            'type': 'Author',
            'source': 'system',
            'properties': {'name': author},
        })
        edges.append({'source': paper_key, 'target': key, 'type': 'AUTHORED_BY', 'properties': {}})
    bound = document.get('keywords') or []
    names = []
    for item in bound:
        if isinstance(item, dict):
            names.append(item.get('name') or '')
        else:
            names.append(str(item))
    names = [item for item in names if item]
    if not names:
        names = _keywords(
            document.get('title') or '',
            f"{document.get('description') or ''} {extra_text}",
        )
        source = 'heuristic'
    else:
        source = 'bound'
    for keyword in names:
        key = 'keyword:' + _slug(keyword)
        nodes.append({
            'key': key,
            'label': keyword,
            'type': 'Keyword',
            'source': source,
            'properties': {'term': keyword},
        })
        edges.append({'source': paper_key, 'target': key, 'type': 'HAS_KEYWORD', 'properties': {}})
    return {'nodes': nodes, 'edges': edges}


def merge_graphs(base: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    if not extra:
        return base
    nodes = {n['key']: n for n in base.get('nodes') or []}
    for node in extra.get('nodes') or []:
        key = str(node.get('key') or '').strip()
        if not key:
            continue
        if key not in nodes:
            nodes[key] = {
                'key': key,
                'label': str(node.get('label') or key),
                'type': str(node.get('type') or 'Concept'),
                'source': str(node.get('source') or 'ai'),
                'properties': node.get('properties') or {},
            }
        else:
            props = dict(nodes[key].get('properties') or {})
            props.update(node.get('properties') or {})
            nodes[key]['properties'] = props
    edges = list(base.get('edges') or [])
    seen = {(e['source'], e['target'], e['type']) for e in edges}
    for edge in extra.get('edges') or []:
        item = {
            'source': str(edge.get('source') or ''),
            'target': str(edge.get('target') or ''),
            'type': str(edge.get('type') or 'RELATED_TO'),
            'properties': edge.get('properties') or {},
        }
        mark = (item['source'], item['target'], item['type'])
        if item['source'] and item['target'] and mark not in seen:
            edges.append(item)
            seen.add(mark)
    return {'nodes': list(nodes.values()), 'edges': edges}


def localize_graph_heuristic(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    for node in graph.get('nodes') or []:
        item = dict(node)
        node_type = str(item.get('type') or item.get('node_type') or 'Concept')
        item['type'] = node_type
        item['label_zh'] = translate_label(str(item.get('label') or ''))
        item['type_zh'] = TYPE_ZH.get(node_type, node_type)
        nodes.append(item)
    edges = []
    for edge in graph.get('edges') or []:
        item = dict(edge)
        rel = str(item.get('type') or item.get('rel_type') or 'RELATED_TO')
        item['type'] = rel
        item['type_zh'] = translate_rel(rel)
        edges.append(item)
    return {'nodes': nodes, 'edges': edges}


def _merge_zh_overlay(graph: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, Any]:
    base = localize_graph_heuristic(graph)
    if not overlay:
        return base
    by_key = {}
    for node in overlay.get('nodes') or []:
        key = str(node.get('key') or '').strip()
        if key:
            by_key[key] = node
    for node in base['nodes']:
        extra = by_key.get(str(node.get('key') or node.get('node_key') or '')) or {}
        label_zh = str(extra.get('label_zh') or '').strip()
        type_zh = str(extra.get('type_zh') or extra.get('node_type_zh') or '').strip()
        if label_zh:
            node['label_zh'] = label_zh
        if type_zh:
            node['type_zh'] = type_zh
    edge_map = {}
    for edge in overlay.get('edges') or []:
        mark = (
            str(edge.get('source') or ''),
            str(edge.get('target') or ''),
            str(edge.get('type') or edge.get('rel_type') or ''),
        )
        if mark[0] and mark[1]:
            edge_map[mark] = edge
    for edge in base['edges']:
        extra = edge_map.get((edge['source'], edge['target'], edge['type'])) or {}
        type_zh = str(extra.get('type_zh') or extra.get('rel_type_zh') or '').strip()
        if type_zh:
            edge['type_zh'] = type_zh
    return base


def localize_graph(
    kg: KnowledgeGraph,
    settings: Settings,
    graph: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    localized = localize_graph_heuristic(graph)
    if not settings.ai_ready or not (graph.get('nodes') or []):
        return localized, ''
    from kms.ai_client import AiRequestError, chat_json

    compact = {
        'nodes': [
            {
                'key': node.get('key'),
                'label': node.get('label'),
                'type': node.get('type') or node.get('node_type'),
            }
            for node in graph.get('nodes') or []
        ],
        'edges': [
            {
                'source': edge.get('source'),
                'target': edge.get('target'),
                'type': edge.get('type') or edge.get('rel_type'),
            }
            for edge in graph.get('edges') or []
        ],
    }
    try:
        overlay = chat_json(
            settings,
            [
                {'role': 'system', 'content': kg.get_prompt(PROMPT_LOCALIZE)},
                {'role': 'user', 'content': json.dumps(compact, ensure_ascii=False)},
            ],
        )
        return _merge_zh_overlay(graph, overlay), ''
    except Exception as exc:
        detail = str(exc)
        if isinstance(exc, AiRequestError):
            return localized, f'中文图谱生成失败：{detail}'
        return localized, f'中文图谱生成失败：{detail}'


def backfill_graph_zh(kg: KnowledgeGraph, run_id: int) -> dict[str, Any]:
    payload = kg.graph_payload(run_id)
    if not payload.get('nodes') or not kg.graph_needs_zh(run_id):
        return payload
    localized = localize_graph_heuristic(graph_as_extract(payload))
    run = kg.get_run(run_id) or {}
    kg.save_graph_zh(run_id, localized, run.get('zh_status') or 'heuristic')
    return kg.graph_payload(run_id)


def translate_existing_graph(
    kg: KnowledgeGraph,
    settings: Settings,
    document_id: int,
    *,
    ai: bool = True,
) -> dict[str, Any]:
    latest = kg.latest_run(document_id)
    if not latest:
        raise ValueError('还没有图谱，请先抽取')
    payload = kg.graph_payload(latest['id'])
    graph = graph_as_extract(payload)
    if not graph['nodes']:
        raise ValueError('图谱为空，请先抽取')
    zh_error = ''
    if ai:
        localized, zh_error = localize_graph(kg, settings, graph)
        status = 'ai' if settings.ai_ready and not zh_error else 'heuristic'
    else:
        localized = localize_graph_heuristic(graph)
        status = 'heuristic'
    kg.save_graph_zh(latest['id'], localized, status)
    payload = kg.graph_payload(latest['id'])
    if zh_error:
        payload['zh_error'] = zh_error
    return payload


def fallback_metadata(filename: str, current: dict[str, Any]) -> dict[str, Any]:
    stem = re.sub(r'\.pdf$', '', filename, flags=re.I)
    title = (current.get('title') or '').strip() or stem.replace('_', ' ').replace('-', ' ')
    return {
        'title': title,
        'authors': (current.get('authors') or '').strip(),
        'doi': (current.get('doi') or '').strip(),
        'year': (current.get('year') or '').strip(),
        'description': (current.get('description') or '').strip(),
        'keywords': parse_keyword_names(current.get('keywords')),
        'ai_used': False,
    }


def _split_authors(text: str) -> list[str]:
    parts = re.split(r',|;| and |\u4e0e', text)
    return [item.strip() for item in parts if item.strip()]


def _keywords(title: str, abstract: str) -> list[str]:
    blob = f'{title} {abstract}'
    tokens = re.findall(r'[A-Za-z][A-Za-z0-9\-+]{2,}|[\u4e00-\u9fff]{2,}', blob)
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        norm = token.lower()
        if norm in _STOP or norm in seen:
            continue
        seen.add(norm)
        out.append(token)
        if len(out) >= 12:
            break
    return out


def _slug(text: str) -> str:
    text = (text or '').strip().lower()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^a-z0-9\-\u4e00-\u9fff]+', '', text)
    return text[:80] or 'unknown'


def _keep(current: dict[str, str], parsed: dict[str, Any], key: str) -> str:
    existing = (current.get(key) or '').strip()
    if existing:
        return existing
    return str(parsed.get(key) or '').strip()


def parse_metadata_fields(
    settings: Settings,
    kg: KnowledgeGraph,
    filename: str,
    current: dict[str, Any],
) -> dict[str, Any]:
    result = fallback_metadata(filename, current)
    if not settings.ai_ready:
        return result
    from kms.ai_client import chat_json

    try:
        parsed = chat_json(
            settings,
            [
                {'role': 'system', 'content': kg.get_prompt(PROMPT_METADATA)},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {'filename': filename, **current},
                        ensure_ascii=False,
                    ),
                },
            ],
        )
    except Exception as exc:
        result['ai_error'] = str(exc)
        return result
    year = _keep(current, parsed, 'year')
    if year and not re.fullmatch(r'(?:19|20)\d{2}', year):
        year = result['year']
    keywords = parse_keyword_names(current.get('keywords'))
    if not keywords:
        keywords = parse_keyword_names(parsed.get('keywords'))
    return {
        'title': _keep(current, parsed, 'title') or result['title'],
        'authors': _keep(current, parsed, 'authors'),
        'doi': _keep(current, parsed, 'doi'),
        'year': year,
        'description': _keep(current, parsed, 'description'),
        'keywords': keywords,
        'ai_used': True,
    }


DEFAULT_EXTRACT_SCHEMA = (
    '{\n'
    '  "nodes": [\n'
    '    {\n'
    '      "key": "string",\n'
    '      "label": "string",\n'
    '      "type": "Paper|Author|Institution|Keyword|Concept|Material|Process|Metric|File|Year",\n'
    '      "properties": {"evidence": "string"}\n'
    '    }\n'
    '  ],\n'
    '  "edges": [\n'
    '    {"source": "string", "target": "string", "type": "string", "properties": {}}\n'
    '  ]\n'
    '}'
)


def resolve_extract_prompt(
    kg: KnowledgeGraph,
    keywords: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    default = kg.get_prompt(PROMPT_EXTRACT)
    parts: list[str] = [default]
    used: list[str] = []
    for item in keywords or []:
        name = str(item.get('name') or '').strip()
        body = str(item.get('extract_prompt') or '').strip()
        schema = str(item.get('extract_schema') or '').strip()
        if not body and not schema:
            continue
        heading = name or 'keyword'
        section = f'## Keyword: {heading}'
        if body:
            section += f'\n{body}'
        if schema:
            section += f'\nOutput schema for {heading}:\n{schema}'
        parts.append(section)
        used.append(name or heading)
    suffix = (
        '\n\nAlways keep the Paper node. Only use facts from the provided chunk text. '
        'Do not invent experimental values. Return JSON only with nodes and edges.'
    )
    if not used:
        return default, PROMPT_EXTRACT
    label = 'keyword:' + ','.join(used[:4])
    return '\n\n'.join(parts) + suffix, label


def extract_document_graph(
    kg: KnowledgeGraph,
    document: dict[str, Any],
    settings: Settings,
    created_by: str,
    *,
    chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from kms.ai_client import chat_json
    from kms.pdf_parse import extractable_chunks

    keywords = document.get('keywords') or []
    prompt_body, prompt_name = resolve_extract_prompt(kg, keywords)
    body_chunks = extractable_chunks(chunks or [])
    extra_text = ' '.join((item.get('text') or '')[:1200] for item in body_chunks[:3])
    base = system_graph(document, extra_text=extra_text)
    extra = None
    raw = ''
    error = ''
    model = 'heuristic'
    used = 0
    if settings.ai_ready and body_chunks:
        from kms.ai_client import AiRequestError

        model = settings.ai_model
        merged_extra: dict[str, Any] = {'nodes': [], 'edges': []}
        errors: list[str] = []
        for chunk in body_chunks:
            try:
                piece = chat_json(
                    settings,
                    [
                        {'role': 'system', 'content': prompt_body},
                        {
                            'role': 'user',
                            'content': json.dumps(
                                {
                                    'paper': _paper_extract_fields(document, keywords),
                                    'chunk': {
                                        'index': chunk.get('chunk_index'),
                                        'section': chunk.get('section') or '',
                                        'page_from': chunk.get('page_from'),
                                        'page_to': chunk.get('page_to'),
                                        'text': chunk.get('text') or '',
                                    },
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                )
                merged_extra = merge_graphs(merged_extra, piece)
                used += 1
            except Exception as exc:
                errors.append(f"chunk {chunk.get('chunk_index')}: {exc}")
                if isinstance(exc, AiRequestError) and 'HTTP 4' in str(exc):
                    break
        extra = merged_extra
        raw = json.dumps(extra, ensure_ascii=False)
        if errors:
            error = '; '.join(errors[:4])
            if not used:
                extra = None
                raw = ''
    elif not settings.ai_ready:
        model = 'heuristic'
    graph = merge_graphs(base, extra)
    graph, zh_error = localize_graph(kg, settings, graph)
    if zh_error:
        error = f'{error}; {zh_error}'.strip('; ')
    run_id = kg.create_run(
        document,
        created_by=created_by,
        model=model,
        graph=graph,
        raw_json=raw,
        error=error,
        prompt_name=prompt_name,
    )
    zh_status = 'ai' if settings.ai_ready and not zh_error else 'heuristic'
    kg.save_graph_zh(run_id, graph, zh_status)
    payload = kg.graph_payload(run_id)
    payload['extracted_chunks'] = used or len(body_chunks)
    return payload


def _paper_extract_fields(document: dict[str, Any], keywords: list[Any]) -> dict[str, Any]:
    return {
        'id': document.get('id'),
        'title': document.get('title') or '',
        'authors': document.get('authors') or '',
        'doi': document.get('doi') or '',
        'year': document.get('year'),
        'abstract': document.get('description') or '',
        'institution': document.get('parent') or '',
        'filename': document.get('original_filename') or '',
        'created_at': document.get('created_at') or '',
        'source': document.get('source') or '',
        'keywords': [
            item.get('name') if isinstance(item, dict) else str(item)
            for item in keywords
        ],
    }
