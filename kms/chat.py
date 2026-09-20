from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from kms.catalog import Catalog, _now
from kms.config import Settings
from kms.keywords import KeywordStore
from kms.kg import PROMPT_CHAT, KnowledgeGraph
from kms.rag import (
    build_answer_prompt,
    retrieve_context,
    tokenize,
)

MAX_MESSAGE_CHARS = 32 * 1024
HISTORY_LIMIT = 12

CHAT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_threads (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_threads_user
    ON chat_threads(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    thread_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_thread
    ON chat_messages(thread_id, id);
"""


def public_thread(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': row['id'],
        'title': row.get('title') or '新对话',
        'created_at': row.get('created_at') or '',
        'updated_at': row.get('updated_at') or '',
    }


def public_message(row: dict[str, Any]) -> dict[str, Any]:
    try:
        sources = json.loads(row.get('sources_json') or '[]')
    except json.JSONDecodeError:
        sources = []
    if not isinstance(sources, list):
        sources = []
    return {
        'id': row['id'],
        'thread_id': row['thread_id'],
        'role': row['role'],
        'content': row.get('content') or '',
        'sources': sources,
        'created_at': row.get('created_at') or '',
    }


def title_from_question(question: str) -> str:
    text = re.sub(r'\s+', ' ', (question or '').strip())
    if len(text) <= 36:
        return text or '新对话'
    return text[:36].rstrip() + '…'


class ChatStore:
    def __init__(self, catalog: Catalog) -> None:
        self.conn = catalog.conn
        self.conn.executescript(CHAT_SCHEMA)
        self.conn.commit()

    def list_threads(self, user_id: int, limit: int = 40) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM chat_threads
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_thread(self, thread_id: int, user_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            'SELECT * FROM chat_threads WHERE id = ? AND user_id = ?',
            (thread_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def create_thread(self, user_id: int, title: str = '') -> dict[str, Any]:
        now = _now()
        cursor = self.conn.execute(
            """
            INSERT INTO chat_threads (user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title or '新对话', now, now),
        )
        self.conn.commit()
        return self.get_thread(int(cursor.lastrowid), user_id) or {
            'id': int(cursor.lastrowid),
            'user_id': user_id,
            'title': title or '新对话',
            'created_at': now,
            'updated_at': now,
        }

    def delete_thread(self, thread_id: int, user_id: int) -> bool:
        thread = self.get_thread(thread_id, user_id)
        if not thread:
            return False
        self.conn.execute('DELETE FROM chat_messages WHERE thread_id = ?', (thread_id,))
        self.conn.execute(
            'DELETE FROM chat_threads WHERE id = ? AND user_id = ?',
            (thread_id, user_id),
        )
        self.conn.commit()
        return True

    def list_messages(self, thread_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM chat_messages
            WHERE thread_id = ?
            ORDER BY id
            """,
            (thread_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_message(
        self,
        thread_id: int,
        role: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        cursor = self.conn.execute(
            """
            INSERT INTO chat_messages (thread_id, role, content, sources_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                role,
                content,
                json.dumps(sources or [], ensure_ascii=False),
                now,
            ),
        )
        self.conn.execute(
            'UPDATE chat_threads SET updated_at = ? WHERE id = ?',
            (now, thread_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            'SELECT * FROM chat_messages WHERE id = ?',
            (int(cursor.lastrowid),),
        ).fetchone()
        return dict(row) if row else {
            'id': int(cursor.lastrowid),
            'thread_id': thread_id,
            'role': role,
            'content': content,
            'sources_json': json.dumps(sources or [], ensure_ascii=False),
            'created_at': now,
        }

    def set_title(self, thread_id: int, title: str) -> None:
        self.conn.execute(
            'UPDATE chat_threads SET title = ?, updated_at = ? WHERE id = ?',
            (title, _now(), thread_id),
        )
        self.conn.commit()


def heuristic_answer(question: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return (
            f'文献库里没有检索到与「{question.strip()}」直接相关的论文。'
            '可以换工艺环节、材料或电池技术再问，或先在文献检索页核对入库记录。'
        )
    lines = [
        f'根据文献库，与「{question.strip()}」最相关的 {len(sources)} 篇是：',
        '',
    ]
    for item in sources:
        year = item.get('year') or '年份未知'
        snippet = item.get('snippet') or ''
        lines.append(f"[{item['index']}] {item.get('title') or '未命名文献'}（{year}）")
        if snippet:
            lines.append(snippet)
        lines.append('')
    lines.append('当前未配置对话模型，以上为检索结果。在「模型与图谱」填写 API 后，可以基于这些文献生成完整回答。')
    return '\n'.join(lines).strip()


def _history_messages(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    keep = [row for row in rows if row.get('role') in {'user', 'assistant'}]
    keep = keep[-HISTORY_LIMIT:]
    return [
        {'role': row['role'], 'content': (row.get('content') or '')[:4000]}
        for row in keep
    ]


def run_turn(
    store: ChatStore,
    catalog: Catalog,
    keys: KeywordStore,
    kg: KnowledgeGraph,
    settings: Settings,
    *,
    user_id: int,
    thread_id: int | None,
    question: str,
) -> Iterator[dict[str, Any]]:
    question = (question or '').strip()
    if not question:
        raise ValueError('消息不能为空')
    if len(question) > MAX_MESSAGE_CHARS:
        raise ValueError('消息过长')

    thread = store.get_thread(thread_id, user_id) if thread_id else None
    created = False
    if not thread:
        thread = store.create_thread(user_id, title_from_question(question))
        created = True
        thread_id = thread['id']
    elif (thread.get('title') or '新对话') == '新对话':
        store.set_title(thread['id'], title_from_question(question))
        thread = store.get_thread(thread['id'], user_id) or thread

    history = store.list_messages(thread['id'])
    store.add_message(thread['id'], 'user', question, [])
    sources = retrieve_context(catalog, keys, kg, question)
    yield {
        'type': 'meta',
        'thread_id': thread['id'],
        'created': created,
        'thread': public_thread(thread),
        'ai_ready': settings.ai_ready,
    }
    yield {'type': 'sources', 'sources': sources}

    answer = ''
    error = ''
    if settings.ai_ready:
        from kms.ai_client import AiRequestError, chat_stream, chat_text

        messages = [
            {'role': 'system', 'content': kg.get_prompt(PROMPT_CHAT)},
            *_history_messages(history),
            {
                'role': 'user',
                'content': build_answer_prompt(question, sources),
            },
        ]
        try:
            for piece in chat_stream(settings, messages):
                answer += piece
                yield {'type': 'delta', 'content': piece}
        except Exception as exc:
            if not answer:
                try:
                    answer = chat_text(settings, messages)
                    if answer:
                        yield {'type': 'delta', 'content': answer}
                except Exception as fallback_exc:
                    error = str(fallback_exc)
            if not answer:
                error = error or str(exc)
    if not answer:
        if error:
            prefix = f'模型调用失败，已回退为检索结果。{error}\n\n'
            answer = prefix + heuristic_answer(question, sources)
            yield {'type': 'delta', 'content': answer}
        else:
            answer = heuristic_answer(question, sources)
            yield {'type': 'delta', 'content': answer}

    saved = store.add_message(thread['id'], 'assistant', answer, sources)
    yield {
        'type': 'done',
        'status': 'completed',
        'thread_id': thread['id'],
        'message': public_message(saved),
        'thread': public_thread(store.get_thread(thread['id'], user_id) or thread),
    }


def collect_turn(
    store: ChatStore,
    catalog: Catalog,
    keys: KeywordStore,
    kg: KnowledgeGraph,
    settings: Settings,
    *,
    user_id: int,
    thread_id: int | None,
    question: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'thread_id': thread_id,
        'sources': [],
        'content': '',
        'message': None,
        'thread': None,
        'ai_ready': False,
    }
    for event in run_turn(
        store,
        catalog,
        keys,
        kg,
        settings,
        user_id=user_id,
        thread_id=thread_id,
        question=question,
    ):
        kind = event.get('type')
        if kind == 'meta':
            payload['thread_id'] = event.get('thread_id')
            payload['thread'] = event.get('thread')
            payload['ai_ready'] = event.get('ai_ready')
        elif kind == 'sources':
            payload['sources'] = event.get('sources') or []
        elif kind == 'delta':
            payload['content'] += str(event.get('content') or '')
        elif kind == 'done':
            payload['message'] = event.get('message')
            payload['thread'] = event.get('thread') or payload['thread']
            payload['thread_id'] = event.get('thread_id') or payload['thread_id']
    return payload
