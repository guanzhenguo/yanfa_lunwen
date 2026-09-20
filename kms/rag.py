from __future__ import annotations

import re
from typing import Any

from kms.catalog import Catalog
from kms.keywords import KeywordStore
from kms.kg import KnowledgeGraph

RETRIEVE_LIMIT = 6
RECALL_TOP_K = 20
CHUNK_PACK_LIMIT = 8
CHUNK_TEXT_LIMIT = 1200
RRF_K = 60.0
VECTOR_WEIGHT = 1.0
BM25_WEIGHT = 1.0
GRAPH_WEIGHT = 0.8
TITLE_WEIGHT = 0.9

_LATIN = re.compile(r'[A-Za-z][A-Za-z0-9+\-]{1,}')
_HAN_RUN = re.compile(r'[\u4e00-\u9fff]+')


def tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    blob = text or ''
    for word in _LATIN.findall(blob):
        tokens.add(word.lower())
    for run in _HAN_RUN.findall(blob):
        if len(run) <= 2:
            tokens.add(run)
            continue
        tokens.add(run)
        for index in range(len(run) - 1):
            tokens.add(run[index : index + 2])
    return tokens


def chunk_id(document_id: int, chunk_index: int) -> str:
    return f'{int(document_id)}:{int(chunk_index)}'


def rrf_fuse(
    ranked_lists: list[tuple[list[dict[str, Any]], float, str]],
    *,
    rrf_k: float = RRF_K,
) -> list[dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}
    for items, weight, source in ranked_lists:
        for rank, chunk in enumerate(items, start=1):
            key = str(chunk.get('chunk_id') or '')
            if not key:
                continue
            score = max(weight, 0.0) / (rrf_k + rank)
            existing = fused.get(key)
            if existing is None:
                existing = {**chunk, 'fusion_score': 0.0, 'fusion_sources': []}
                fused[key] = existing
            existing['fusion_score'] += score
            existing['score'] = existing['fusion_score']
            if source not in existing['fusion_sources']:
                existing['fusion_sources'].append(source)
            if source == 'graph' and chunk.get('graph_score') is not None:
                existing['graph_score'] = chunk['graph_score']
            if source == 'bm25' and chunk.get('bm25_score') is not None:
                existing['bm25_score'] = chunk['bm25_score']
    return sorted(fused.values(), key=lambda item: item.get('fusion_score', 0.0), reverse=True)


def retrieve_context(
    catalog: Catalog,
    keys: KeywordStore,
    kg: KnowledgeGraph,
    question: str,
    *,
    limit: int = RETRIEVE_LIMIT,
) -> list[dict[str, Any]]:
    query = (question or '').strip()
    if not query:
        return []
    query_tokens = tokenize(query)
    search_tokens = query_tokens | _bridge_tokens(kg, query_tokens)
    expanded = _expanded_query(query, search_tokens)
    lexical = _lexical_chunks(catalog, query, search_tokens)
    bm25 = _bm25_chunks(catalog, expanded)
    graph = _graph_chunks(catalog, kg, query, search_tokens)
    title = _title_chunks(catalog, keys, query, search_tokens)
    fused = rrf_fuse([
        (lexical, VECTOR_WEIGHT, 'vector'),
        (bm25, BM25_WEIGHT, 'bm25'),
        (graph, GRAPH_WEIGHT, 'graph'),
        (title, TITLE_WEIGHT, 'title'),
    ])
    reranked = _rerank_chunks(query, search_tokens, fused)
    return _group_paper_sources(
        catalog,
        keys,
        kg,
        reranked,
        search_tokens,
        limit=limit,
    )


def format_source_context(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return '（文献库未检索到相关论文）'
    blocks = []
    for item in sources:
        year = item.get('year') or '年份未知'
        keywords = '、'.join(item.get('keywords') or []) or '无'
        graph = '、'.join(item.get('graph') or []) or '无'
        triples = '；'.join(item.get('triples') or []) or '无'
        passages = item.get('chunks') or []
        if passages:
            body = '\n'.join(
                _format_passage(chunk) for chunk in passages[:3]
            )
        else:
            body = item.get('snippet') or '无'
        blocks.append(
            f"文档 {item['index']}:\n"
            f"{item.get('title') or '未命名文献'} ({year}; DOI {item.get('doi') or '无'})\n"
            f"作者：{item.get('authors') or '未知'}\n"
            f"关键词：{keywords}\n"
            f"图谱：{graph}\n"
            f"三元组：{triples}\n"
            f"{body}"
        )
    return '\n\n'.join(blocks)


def build_answer_prompt(question: str, sources: list[dict[str, Any]]) -> str:
    return (
        '基于以下上下文信息，请回答用户的问题。\n\n'
        f'上下文信息：\n{format_source_context(sources)}\n\n'
        f'用户问题：{question}\n\n'
        '请根据上下文信息准确回答问题。数值必须来自摘录或三元组，不要编造实验数据。\n'
        '如果上下文中缺少相关信息，请明确说明缺口，并列出最相关的论文。\n'
        '引用文献时使用 [1]、[2] 这种序号，对应上面的文档编号。'
    )


def _format_passage(chunk: dict[str, Any]) -> str:
    page_from = chunk.get('page_from') or 0
    page_to = chunk.get('page_to') or page_from
    page = f'p.{page_from}–{page_to}' if page_from else ''
    section = chunk.get('section') or ''
    loc = ' · '.join(part for part in (section, page) if part)
    text = re.sub(r'\s+', ' ', str(chunk.get('text') or '')).strip()
    if len(text) > CHUNK_TEXT_LIMIT:
        text = text[:CHUNK_TEXT_LIMIT].rstrip() + '…'
    prefix = f'正文摘录（{loc}）' if loc else '正文摘录'
    return f'{prefix}：{text or "无"}'


def _bridge_tokens(kg: KnowledgeGraph, query_tokens: set[str]) -> set[str]:
    extra: set[str] = set()
    tokens = [item for item in query_tokens if len(item) >= 2][:10]
    if not tokens:
        return extra
    for token in tokens:
        like = f'%{token}%'
        rows = kg.conn.execute(
            """
            SELECT DISTINCT label, label_zh
            FROM kg_nodes
            WHERE node_type NOT IN ('Paper', 'File')
              AND (label_zh LIKE ? OR label LIKE ?)
            LIMIT 16
            """,
            (like, like),
        ).fetchall()
        for row in rows:
            extra |= tokenize(row['label'] or '')
            extra |= tokenize(row['label_zh'] or '')
    return extra - query_tokens


def _expanded_query(query: str, search_tokens: set[str]) -> str:
    extras = [
        token
        for token in sorted(search_tokens)
        if _LATIN.fullmatch(token) and token.lower() not in query.lower()
    ][:8]
    if not extras:
        return query
    return f'{query} {" ".join(extras)}'


def _select_body_chunks(
    catalog: Catalog,
    document_id: int,
    query_tokens: set[str],
    *,
    fusion_sources: list[str],
    score: float,
) -> list[dict[str, Any]]:
    rows = catalog.list_chunks(document_id)
    if not rows:
        return []
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for row in rows:
        item = dict(row)
        item['document_id'] = document_id
        overlap = len(query_tokens & tokenize(item.get('text') or ''))
        ranked.append((overlap, int(item.get('chunk_index') or 0), item))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]))
    chosen = [item for overlap, _, item in ranked if overlap > 0][:3]
    if not chosen:
        chosen = [item for _, _, item in ranked[:2]]
    out = []
    for item in chosen:
        chunk = _as_chunk(item, score=score, source='body')
        chunk['fusion_sources'] = list(fusion_sources)
        out.append(chunk)
    return out


def _as_chunk(
    row: dict[str, Any],
    *,
    score: float,
    source: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc_id = int(row.get('document_id') or row.get('id') or 0)
    index = int(row.get('chunk_index') or 0)
    item = {
        'chunk_id': chunk_id(doc_id, index),
        'document_id': doc_id,
        'chunk_index': index,
        'section': row.get('section') or '',
        'page_from': int(row.get('page_from') or 0),
        'page_to': int(row.get('page_to') or 0),
        'text': row.get('text') or '',
        'score': float(score),
        'fusion_sources': [source],
    }
    if extra:
        item.update(extra)
    return item


def _bm25_chunks(catalog: Catalog, query: str) -> list[dict[str, Any]]:
    rows = catalog.search_chunks_bm25(query, limit=RECALL_TOP_K)
    out = []
    for row in rows:
        score = float(row.get('score') or 0.0)
        item = _as_chunk(row, score=score, source='bm25', extra={'bm25_score': score})
        out.append(item)
    return out


def _lexical_chunks(
    catalog: Catalog,
    query: str,
    query_tokens: set[str],
) -> list[dict[str, Any]]:
    tokens = [item for item in query_tokens if len(item) >= 2][:8]
    if not tokens:
        return []
    scored: dict[str, dict[str, Any]] = {}
    for token in tokens:
        like = f'%{token}%'
        rows = catalog.conn.execute(
            """
            SELECT id, document_id, chunk_index, section, page_from, page_to, text
            FROM paper_chunks
            WHERE text LIKE ?
            LIMIT 30
            """,
            (like,),
        ).fetchall()
        for row in rows:
            item = _as_chunk(dict(row), score=0.0, source='vector')
            key = item['chunk_id']
            overlap = len(query_tokens & tokenize(item['text']))
            item['score'] = float(overlap)
            current = scored.get(key)
            if current is None or item['score'] > current['score']:
                scored[key] = item
    ranked = sorted(scored.values(), key=lambda item: item['score'], reverse=True)
    return ranked[:RECALL_TOP_K]


def _title_chunks(
    catalog: Catalog,
    keys: KeywordStore,
    query: str,
    query_tokens: set[str],
) -> list[dict[str, Any]]:
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    terms = [query] + [token for token in query_tokens if len(token) >= 2][:8]
    for term in terms:
        for row in catalog.search(q=term, limit=RECALL_TOP_K):
            doc_id = int(row['id'])
            if doc_id in seen:
                continue
            seen.add(doc_id)
            rows.append(row)
    out = []
    for row in rows:
        keywords = keys.keywords_for(row['id'])
        keyword_text = ' '.join(item.get('name') or '' for item in keywords)
        blob = ' '.join([
            row.get('title') or '',
            row.get('description') or '',
            keyword_text,
        ])
        score = 2 * len(query_tokens & tokenize(blob))
        if query.lower() in (row.get('title') or '').lower():
            score += 6
        excerpt = catalog.matching_chunk_excerpt(row['id'], query_tokens)
        text = excerpt or blob
        out.append(_as_chunk(
            {
                'document_id': row['id'],
                'chunk_index': -1,
                'section': 'Metadata',
                'page_from': 0,
                'page_to': 0,
                'text': text,
            },
            score=float(score),
            source='title',
        ))
    out.sort(key=lambda item: item['score'], reverse=True)
    return out[:RECALL_TOP_K]


def _graph_chunks(
    catalog: Catalog,
    kg: KnowledgeGraph,
    query: str,
    query_tokens: set[str],
) -> list[dict[str, Any]]:
    tokens = [item for item in query_tokens if len(item) >= 2][:8]
    if not tokens:
        return []
    doc_scores: dict[int, float] = {}
    for token in tokens:
        like = f'%{token}%'
        rows = kg.conn.execute(
            """
            SELECT DISTINCT document_id AS id
            FROM kg_nodes
            WHERE label LIKE ? OR label_zh LIKE ? OR properties_json LIKE ?
            LIMIT 20
            """,
            (like, like, like),
        ).fetchall()
        for row in rows:
            doc_id = int(row['id'])
            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + 1.0
    out = []
    for doc_id, graph_score in sorted(doc_scores.items(), key=lambda item: -item[1]):
        excerpt = catalog.matching_chunk_excerpt(doc_id, query_tokens)
        labels = _graph_labels(kg, doc_id)
        text = excerpt or '；'.join(labels[:12])
        out.append(_as_chunk(
            {
                'document_id': doc_id,
                'chunk_index': -2,
                'section': 'Graph',
                'page_from': 0,
                'page_to': 0,
                'text': text,
            },
            score=float(graph_score),
            source='graph',
            extra={'graph_score': float(graph_score)},
        ))
        if len(out) >= RECALL_TOP_K:
            break
    return out


def _rerank_chunks(
    query: str,
    query_tokens: set[str],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lowered = query.lower()
    ranked = []
    for chunk in chunks:
        text = (chunk.get('text') or '')
        overlap = len(query_tokens & tokenize(text))
        bonus = 2.0 if lowered and lowered in text.lower() else 0.0
        graph_bonus = 1.2 if 'graph' in (chunk.get('fusion_sources') or []) else 0.0
        bm25_bonus = 1.0 if 'bm25' in (chunk.get('fusion_sources') or []) else 0.0
        chunk = dict(chunk)
        chunk['rerank_score'] = (
            float(chunk.get('fusion_score') or 0.0) * 12
            + overlap * 1.5
            + bonus
            + graph_bonus
            + bm25_bonus
        )
        ranked.append(chunk)
    ranked.sort(key=lambda item: item.get('rerank_score', 0.0), reverse=True)
    return ranked[: max(RECALL_TOP_K, CHUNK_PACK_LIMIT)]


def _group_paper_sources(
    catalog: Catalog,
    keys: KeywordStore,
    kg: KnowledgeGraph,
    chunks: list[dict[str, Any]],
    query_tokens: set[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    order: list[int] = []
    packed = 0
    for chunk in chunks:
        doc_id = int(chunk.get('document_id') or 0)
        if not doc_id:
            continue
        if doc_id not in grouped:
            if len(order) >= limit:
                continue
            grouped[doc_id] = []
            order.append(doc_id)
        if chunk.get('chunk_index', 0) < 0 and grouped[doc_id]:
            continue
        if len(grouped[doc_id]) >= 3:
            continue
        grouped[doc_id].append(chunk)
        packed += 1
        if packed >= CHUNK_PACK_LIMIT and len(order) >= limit:
            break
    sources = []
    for index, doc_id in enumerate(order, start=1):
        row = catalog.get_by_id(doc_id)
        if not row:
            continue
        keywords = keys.keywords_for(doc_id)
        graph_labels = _graph_labels(kg, doc_id)
        triples = kg.latest_triples(doc_id)
        seed = grouped.get(doc_id) or []
        fusion_sources = sorted({
            source
            for chunk in seed
            for source in (chunk.get('fusion_sources') or [])
        })
        score = max(
            (float(item.get('rerank_score') or item.get('score') or 0.0) for item in seed),
            default=0.0,
        )
        passages = _select_body_chunks(
            catalog,
            doc_id,
            query_tokens,
            fusion_sources=fusion_sources,
            score=score,
        ) or [item for item in seed if int(item.get('chunk_index') or 0) >= 0] or seed
        snippet = ''
        page_from = 0
        page_to = 0
        for chunk in passages:
            text = re.sub(r'\s+', ' ', chunk.get('text') or '').strip()
            if text:
                snippet = text
                page_from = int(chunk.get('page_from') or 0)
                page_to = int(chunk.get('page_to') or 0)
                break
        if len(snippet) > 360:
            snippet = snippet[:360].rstrip() + '…'
        if not snippet:
            snippet = '；'.join(item.get('name') or '' for item in keywords[:8]) or (row.get('title') or '')
        pages = [
            (int(item.get('page_from') or 0), int(item.get('page_to') or 0))
            for item in passages
            if int(item.get('page_from') or 0)
        ]
        if pages:
            page_from = min(item[0] for item in pages)
            page_to = max(item[1] or item[0] for item in pages)
        sources.append({
            'index': index,
            'paper_id': doc_id,
            'title': row.get('title') or '',
            'authors': row.get('authors') or '',
            'year': row.get('year'),
            'doi': row.get('doi') or '',
            'has_pdf': bool(row.get('storage_key')),
            'keywords': [item.get('name') or '' for item in keywords if item.get('name')],
            'graph': graph_labels[:8],
            'triples': triples,
            'snippet': snippet,
            'page_from': page_from,
            'page_to': page_to,
            'score': round(score, 3),
            'fusion_sources': fusion_sources,
            'chunks': [
                {
                    'chunk_index': chunk.get('chunk_index'),
                    'section': chunk.get('section') or '',
                    'page_from': chunk.get('page_from') or 0,
                    'page_to': chunk.get('page_to') or 0,
                    'text': chunk.get('text') or '',
                    'score': round(float(chunk.get('rerank_score') or chunk.get('score') or 0.0), 3),
                    'fusion_sources': chunk.get('fusion_sources') or fusion_sources,
                }
                for chunk in passages
                if int(chunk.get('chunk_index') or 0) >= 0
            ],
        })
    return sources


def _graph_labels(kg: KnowledgeGraph, document_id: int) -> list[str]:
    latest = kg.latest_run(document_id)
    if not latest or latest.get('status') not in {'pending_review', 'approved'}:
        return []
    rows = kg.conn.execute(
        """
        SELECT COALESCE(NULLIF(label_zh, ''), label) AS label, node_type FROM kg_nodes
        WHERE run_id = ? AND node_type NOT IN ('Paper', 'File')
        ORDER BY id
        """,
        (latest['id'],),
    ).fetchall()
    labels: list[str] = []
    seen: set[str] = set()
    for row in rows:
        label = (row['label'] or '').strip()
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        labels.append(label)
    return labels
