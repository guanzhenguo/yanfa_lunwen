from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response as RawResponse, StreamingResponse

from kms.auth import Accounts, public_user
from kms.catalog import Catalog, public_document
from kms.config import (
    PROJECT_ROOT,
    load_settings,
    public_ai_settings,
    public_neo4j_settings,
    update_ai_settings,
    update_neo4j_settings,
)
from kms.chat import (
    ChatStore,
    collect_turn,
    public_message,
    public_thread,
    run_turn,
)
from kms.keywords import KeywordStore, parse_keyword_names, public_keyword
from kms.kg import (
    DEFAULT_EXTRACT_SCHEMA,
    PROMPT_EXTRACT,
    KnowledgeGraph,
    backfill_graph_zh,
    extract_document_graph,
    parse_metadata_fields,
    translate_existing_graph,
)
from kms.pdf_parse import ParseError, ensure_document_parse
from kms.storage import create_store, object_key, sha256_file

WEB_DIST = PROJECT_ROOT / 'frontend' / 'dist'
COOKIE = 'kms_session'
MAX_UPLOAD = 80 * 1024 * 1024


def _db():
    cat = Catalog(load_settings().catalog_path)
    acc = Accounts(cat)
    kg = KnowledgeGraph(cat)
    keys = KeywordStore(cat)
    try:
        yield cat, acc, kg, keys
    finally:
        cat.close()


def _authed(request: Request, db=Depends(_db)):
    cat, acc, kg, keys = db
    user = acc.user_from_token(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail='login required')
    return cat, acc, kg, keys, user


def _admin(ctx=Depends(_authed)):
    cat, acc, kg, keys, user = ctx
    if user['role'] != 'admin':
        raise HTTPException(status_code=403, detail='admin only')
    return cat, acc, kg, keys, user


def _set_session(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite='lax',
        max_age=7 * 24 * 3600,
        path='/',
    )


def _filename_title(name: str) -> str:
    stem = Path(name or 'upload').stem
    title = re.sub(r'[_-]+', ' ', stem).strip()
    return title or stem or 'untitled'


def _paper_payload(row: dict, keys: KeywordStore) -> dict:
    item = public_document(row)
    item['keywords'] = [
        public_keyword(keyword, include_prompt=False)
        for keyword in keys.keywords_for(row['id'])
    ]
    return item


def _paper_list(rows: list[dict], keys: KeywordStore) -> list[dict]:
    mapping = keys.keywords_for_many([row['id'] for row in rows])
    out = []
    for row in rows:
        item = public_document(row)
        item['keywords'] = [
            public_keyword(keyword, include_prompt=False)
            for keyword in mapping.get(row['id'], [])
        ]
        out.append(item)
    return out


def _empty_parse(row: dict) -> dict:
    return {
        'document_id': row.get('id'),
        'status': 'none',
        'parser': '',
        'sha256': '',
        'page_count': 0,
        'char_count': 0,
        'chunk_count': 0,
        'preview': '',
        'error': '',
        'parsed_at': '',
        'has_pdf': bool(row.get('storage_key')),
        'chunks': [],
    }


def _extract_config(kg: KnowledgeGraph, keys: KeywordStore, doc_id: int) -> dict:
    return {
        'default_prompt': kg.get_prompt(PROMPT_EXTRACT),
        'default_schema': DEFAULT_EXTRACT_SCHEMA,
        'keywords': [public_keyword(item) for item in keys.keywords_for(doc_id)],
    }


def create_app() -> FastAPI:
    app = FastAPI(title='PV Lab Papers', docs_url='/api/docs')
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.get('/api/health')
    def health():
        settings = load_settings()
        return {
            'ok': True,
            'storage': settings.storage_backend,
            'bucket': settings.minio_bucket,
            'ai_ready': settings.ai_ready,
            'neo4j_enabled': settings.neo4j_enabled,
        }

    @app.post('/api/auth/login')
    def login(payload: dict, response: Response, db=Depends(_db)):
        _cat, acc, _kg, _keys = db
        user = acc.authenticate(payload.get('username') or '', payload.get('password') or '')
        if not user:
            raise HTTPException(status_code=401, detail='invalid username or password')
        token = acc.create_session(user['id'])
        _set_session(response, token)
        return public_user(user)

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, db=Depends(_db)):
        _cat, acc, _kg, _keys = db
        acc.delete_session(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path='/')
        return {'ok': True}

    @app.get('/api/auth/me')
    def me(ctx=Depends(_authed)):
        _cat, _acc, _kg, _keys, user = ctx
        return public_user(user)

    @app.get('/api/settings')
    def get_settings(ctx=Depends(_authed)):
        _cat, _acc, _kg, _keys, user = ctx
        settings = load_settings()
        ai = public_ai_settings(settings)
        neo4j = public_neo4j_settings(settings)
        if user['role'] != 'admin':
            ai = {**ai, 'api_key': ''}
            neo4j = {**neo4j, 'password': ''}
        return {'ai': ai, 'neo4j': neo4j}

    @app.put('/api/settings/ai')
    def put_ai_settings(payload: dict, ctx=Depends(_admin)):
        _cat, _acc, _kg, _keys, _user = ctx
        settings = update_ai_settings(payload or {})
        return public_ai_settings(settings)

    @app.put('/api/settings/neo4j')
    def put_neo4j_settings(payload: dict, ctx=Depends(_admin)):
        _cat, _acc, _kg, _keys, _user = ctx
        settings = update_neo4j_settings(payload or {})
        return public_neo4j_settings(settings)

    @app.get('/api/kg/prompts')
    def list_prompts(ctx=Depends(_authed)):
        _cat, _acc, kg, _keys, _user = ctx
        return kg.list_prompts()

    @app.put('/api/kg/prompts/{name}')
    def save_prompt(name: str, payload: dict, ctx=Depends(_admin)):
        _cat, _acc, kg, _keys, user = ctx
        try:
            return kg.save_prompt(name, payload.get('body') or '', user['username'])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get('/api/keywords')
    def list_keywords(ctx=Depends(_authed)):
        _cat, _acc, _kg, keys, _user = ctx
        return [public_keyword(item) for item in keys.list_keywords()]

    @app.post('/api/keywords')
    def create_keyword(payload: dict, ctx=Depends(_authed)):
        _cat, _acc, _kg, keys, user = ctx
        try:
            created = keys.get_or_create(
                payload.get('name') or '',
                updated_by=user['username'],
            )
            if user['role'] == 'admin' and (
                payload.get('extract_prompt') or payload.get('extract_schema')
            ):
                created = keys.update_keyword(
                    created['id'],
                    extract_prompt=str(payload.get('extract_prompt') or ''),
                    extract_schema=str(payload.get('extract_schema') or ''),
                    updated_by=user['username'],
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return public_keyword(created)

    @app.patch('/api/keywords/{keyword_id}')
    def patch_keyword(keyword_id: int, payload: dict, ctx=Depends(_authed)):
        _cat, _acc, _kg, keys, user = ctx
        kwargs = {'updated_by': user['username']}
        if 'name' in payload:
            kwargs['name'] = payload.get('name') or ''
        if 'extract_prompt' in payload or 'extract_schema' in payload:
            if user['role'] != 'admin':
                raise HTTPException(status_code=403, detail='admin only')
            if 'extract_prompt' in payload:
                kwargs['extract_prompt'] = payload.get('extract_prompt') or ''
            if 'extract_schema' in payload:
                kwargs['extract_schema'] = payload.get('extract_schema') or ''
        try:
            updated = keys.update_keyword(keyword_id, **kwargs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return public_keyword(updated)

    @app.get('/api/users')
    def list_users(ctx=Depends(_admin)):
        _cat, acc, _kg, _keys, _user = ctx
        return [public_user(item) for item in acc.list_users()]

    @app.post('/api/users')
    def create_user(payload: dict, ctx=Depends(_admin)):
        _cat, acc, _kg, _keys, _user = ctx
        try:
            user_id = acc.create_user(
                payload.get('username') or '',
                payload.get('password') or '',
                role=payload.get('role') or 'user',
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        users = {item['id']: item for item in acc.list_users()}
        return public_user(users[user_id])

    @app.patch('/api/users/{user_id}')
    def update_user(user_id: int, payload: dict, ctx=Depends(_admin)):
        _cat, acc, _kg, _keys, current = ctx
        if user_id == current['id'] and payload.get('active') is False:
            raise HTTPException(status_code=400, detail='cannot disable yourself')
        try:
            if 'active' in payload:
                acc.set_active(user_id, bool(payload['active']))
            if payload.get('role'):
                acc.set_role(user_id, payload['role'])
            if payload.get('password'):
                acc.set_password(user_id, payload['password'])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        users = {item['id']: item for item in acc.list_users()}
        if user_id not in users:
            raise HTTPException(status_code=404, detail='user not found')
        return public_user(users[user_id])

    @app.get('/api/stats')
    def stats(ctx=Depends(_authed)):
        cat, _acc, _kg, _keys, _user = ctx
        return cat.stats()

    @app.get('/api/papers')
    def list_papers(
        q: str = '',
        doi: str = '',
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        oa: Optional[bool] = Query(default=None),
        has_pdf: Optional[bool] = Query(default=None),
        keyword: str = '',
        keyword_id: Optional[int] = None,
        limit: int = Query(default=200, ge=1, le=500),
        ctx=Depends(_authed),
    ):
        cat, _acc, _kg, keys, _user = ctx
        rows = cat.search(
            q=q,
            doi=doi,
            year_from=year_from,
            year_to=year_to,
            oa=oa,
            has_pdf=has_pdf,
            keyword=keyword,
            keyword_id=keyword_id,
            limit=limit,
        )
        return _paper_list(rows, keys)

    @app.get('/api/papers/{doc_id}')
    def get_paper(doc_id: int, ctx=Depends(_authed)):
        cat, _acc, _kg, keys, _user = ctx
        row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='not found')
        return _paper_payload(row, keys)

    @app.patch('/api/papers/{doc_id}/keywords')
    def patch_paper_keywords(doc_id: int, payload: dict, ctx=Depends(_authed)):
        cat, _acc, _kg, keys, user = ctx
        row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='not found')
        names = payload.get('keywords')
        if names is None:
            names = payload.get('names')
        bound = keys.set_document_keywords(
            doc_id,
            parse_keyword_names(names),
            source='manual',
            updated_by=user['username'],
        )
        item = public_document(row)
        item['keywords'] = [public_keyword(keyword, include_prompt=False) for keyword in bound]
        return item

    @app.get('/api/papers/{doc_id}/pdf')
    def preview_pdf(doc_id: int, ctx=Depends(_authed)):
        cat, _acc, _kg, _keys, _user = ctx
        row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='not found')
        key = row.get('storage_key') or ''
        if not key:
            raise HTTPException(status_code=404, detail='no pdf')
        try:
            data = create_store(load_settings()).get_bytes(key)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        filename = (row.get('original_filename') or row.get('doi') or f'paper-{doc_id}')
        if not str(filename).lower().endswith('.pdf'):
            filename = f'{filename}.pdf'
        quoted = quote(str(filename).replace('/', '_'))
        return RawResponse(
            content=data,
            media_type='application/pdf',
            headers={
                'Content-Disposition': f"inline; filename*=UTF-8''{quoted}",
                'Cache-Control': 'private, max-age=120',
                'X-Content-Type-Options': 'nosniff',
            },
        )

    @app.post('/api/papers/parse-metadata')
    async def parse_metadata(
        title: str = Form(''),
        authors: str = Form(''),
        doi: str = Form(''),
        year: str = Form(''),
        description: str = Form(''),
        keywords: str = Form(''),
        filename: str = Form(''),
        file: UploadFile | None = File(None),
        ctx=Depends(_authed),
    ):
        _cat, _acc, kg, _keys, _user = ctx
        name = filename or (file.filename if file else '') or ''
        current = {
            'title': title or '',
            'authors': authors or '',
            'doi': doi or '',
            'year': year or '',
            'description': description or '',
            'keywords': keywords or '',
        }
        return parse_metadata_fields(load_settings(), kg, name, current)

    @app.post('/api/papers/upload')
    async def upload_paper(
        title: str = Form(''),
        authors: str = Form(''),
        doi: str = Form(''),
        year: str = Form(''),
        description: str = Form(''),
        keywords: str = Form(''),
        file: UploadFile = File(...),
        ctx=Depends(_authed),
    ):
        cat, _acc, _kg, keys, user = ctx
        original_name = file.filename or 'upload.pdf'
        title = (title or '').strip() or _filename_title(original_name)
        raw = await file.read(MAX_UPLOAD + 1)
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(status_code=400, detail='file too large')
        if not raw.startswith(b'%PDF'):
            raise HTTPException(status_code=400, detail='only pdf allowed')

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp_path = tmp.name
                tmp.write(raw)
            digest = sha256_file(tmp_path)
            key = object_key(digest)
            store = create_store(load_settings())
            location = store.put_file(key, Path(tmp_path))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

        year_val = None
        if (year or '').strip().isdigit():
            year_val = int(year.strip())
        doi = (doi or '').strip()
        url = f'upload://{digest}'
        doc_id = cat.upsert_document({
            'doi': doi,
            'url': url,
            'title': title,
            'authors': (authors or '').strip(),
            'published': str(year_val or ''),
            'year': year_val,
            'description': (description or '').strip(),
            'open_access': False,
            'source': 'upload',
            'storage_key': key,
            'sha256': digest,
            'file_location': location,
            'uploaded_by': user['username'],
            'original_filename': original_name,
        })
        keys.set_document_keywords(
            doc_id,
            parse_keyword_names(keywords),
            source='upload',
            updated_by=user['username'],
        )
        row = cat.get_by_id(doc_id)
        return _paper_payload(row or {'id': doc_id}, keys)

    @app.get('/api/papers/{doc_id}/kg')
    def get_paper_graph(doc_id: int, ctx=Depends(_authed)):
        cat, _acc, kg, keys, _user = ctx
        row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='not found')
        latest = kg.latest_run(doc_id)
        extract = _extract_config(kg, keys, doc_id)
        if not latest:
            parse = cat.parse_payload(doc_id, include_text=False) or _empty_parse(row)
            parse['has_pdf'] = bool(row.get('storage_key'))
            return {
                'run': None,
                'nodes': [],
                'edges': [],
                'triples': [],
                'neo4j': {'nodes': [], 'relationships': []},
                'parse': parse,
                'extract': extract,
            }
        backfill_graph_zh(kg, latest['id'])
        payload = kg.graph_payload(latest['id'])
        parse = cat.parse_payload(doc_id, include_text=False) or _empty_parse(row)
        parse['has_pdf'] = bool(row.get('storage_key'))
        payload['parse'] = parse
        payload['extract'] = extract
        return payload

    @app.get('/api/papers/{doc_id}/parse')
    def get_paper_parse(doc_id: int, ctx=Depends(_authed)):
        cat, _acc, _kg, _keys, _user = ctx
        row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='not found')
        payload = cat.parse_payload(doc_id, include_text=False)
        if not payload:
            return _empty_parse(row)
        payload['has_pdf'] = bool(row.get('storage_key'))
        return payload

    @app.post('/api/papers/{doc_id}/parse')
    def parse_paper(doc_id: int, force: bool = Query(default=False), ctx=Depends(_authed)):
        cat, _acc, _kg, _keys, _user = ctx
        row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='not found')
        try:
            payload = ensure_document_parse(
                cat,
                create_store(load_settings()),
                row,
                force=bool(force),
            )
        except ParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        public = cat.parse_payload(doc_id, include_text=False) or payload
        public['has_pdf'] = True
        return public

    @app.post('/api/papers/{doc_id}/kg/extract')
    def extract_paper_graph(doc_id: int, ctx=Depends(_authed)):
        cat, _acc, kg, keys, user = ctx
        row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='not found')
        try:
            parsed = ensure_document_parse(cat, create_store(load_settings()), row)
        except ParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if parsed.get('status') != 'ok':
            raise HTTPException(
                status_code=400,
                detail=parsed.get('error') or '正文为空，无法抽取图谱',
            )
        row['keywords'] = keys.keywords_for(doc_id)
        payload = extract_document_graph(
            kg,
            row,
            load_settings(),
            user['username'],
            chunks=parsed.get('chunks') or [],
        )
        payload['parse'] = cat.parse_payload(doc_id, include_text=False) or parsed
        payload['extract'] = _extract_config(kg, keys, doc_id)
        return payload

    @app.post('/api/papers/{doc_id}/kg/translate')
    def translate_paper_graph(doc_id: int, ctx=Depends(_authed)):
        cat, _acc, kg, keys, _user = ctx
        row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='not found')
        try:
            payload = translate_existing_graph(kg, load_settings(), doc_id, ai=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload['parse'] = cat.parse_payload(doc_id, include_text=False) or _empty_parse(row)
        payload['parse']['has_pdf'] = bool(row.get('storage_key'))
        payload['extract'] = _extract_config(kg, keys, doc_id)
        return payload

    @app.post('/api/kg/runs/{run_id}/review')
    def review_graph(run_id: int, payload: dict, ctx=Depends(_authed)):
        _cat, _acc, kg, _keys, user = ctx
        try:
            run = kg.review_run(
                run_id,
                str(payload.get('status') or ''),
                user['username'],
                str(payload.get('note') or ''),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return kg.graph_payload(run['id'])

    @app.get('/api/chat/threads')
    def list_chat_threads(ctx=Depends(_authed)):
        cat, _acc, _kg, _keys, user = ctx
        store = ChatStore(cat)
        return [public_thread(item) for item in store.list_threads(user['id'])]

    @app.post('/api/chat/threads')
    def create_chat_thread(ctx=Depends(_authed)):
        cat, _acc, _kg, _keys, user = ctx
        store = ChatStore(cat)
        return public_thread(store.create_thread(user['id']))

    @app.get('/api/chat/threads/{thread_id}')
    def get_chat_thread(thread_id: int, ctx=Depends(_authed)):
        cat, _acc, _kg, _keys, user = ctx
        store = ChatStore(cat)
        thread = store.get_thread(thread_id, user['id'])
        if not thread:
            raise HTTPException(status_code=404, detail='thread not found')
        return {
            'thread': public_thread(thread),
            'messages': [public_message(item) for item in store.list_messages(thread_id)],
        }

    @app.delete('/api/chat/threads/{thread_id}')
    def delete_chat_thread(thread_id: int, ctx=Depends(_authed)):
        cat, _acc, _kg, _keys, user = ctx
        store = ChatStore(cat)
        if not store.delete_thread(thread_id, user['id']):
            raise HTTPException(status_code=404, detail='thread not found')
        return {'ok': True}

    def _chat_events(ctx, payload: dict, stream: bool):
        cat, _acc, kg, keys, user = ctx
        store = ChatStore(cat)
        message = str((payload or {}).get('message') or '').strip()
        raw_thread = (payload or {}).get('thread_id')
        thread_id = int(raw_thread) if raw_thread else None
        settings = load_settings()
        if stream:
            def generate():
                try:
                    for event in run_turn(
                        store,
                        cat,
                        keys,
                        kg,
                        settings,
                        user_id=user['id'],
                        thread_id=thread_id,
                        question=message,
                    ):
                        yield json.dumps(event, ensure_ascii=False) + '\n'
                except ValueError as exc:
                    yield json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False) + '\n'
                except Exception as exc:
                    yield json.dumps(
                        {'type': 'error', 'message': f'?????{exc}'},
                        ensure_ascii=False,
                    ) + '\n'
            return StreamingResponse(
                generate(),
                media_type='application/x-ndjson; charset=utf-8',
                headers={'Cache-Control': 'no-store'},
            )
        try:
            return collect_turn(
                store,
                cat,
                keys,
                kg,
                settings,
                user_id=user['id'],
                thread_id=thread_id,
                question=message,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post('/api/chat')
    def chat_ask(payload: dict, stream: bool = Query(default=True), ctx=Depends(_authed)):
        return _chat_events(ctx, payload, stream)

    @app.post('/api/chat/threads/{thread_id}/messages')
    def chat_thread_message(
        thread_id: int,
        payload: dict,
        stream: bool = Query(default=True),
        ctx=Depends(_authed),
    ):
        body = dict(payload or {})
        body['thread_id'] = thread_id
        return _chat_events(ctx, body, stream)

    if WEB_DIST.is_dir():
        app.mount('/', StaticFiles(directory=WEB_DIST, html=True), name='web')

    return app


app = create_app()
