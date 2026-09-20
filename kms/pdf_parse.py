from __future__ import annotations

import re
from typing import Any

import fitz

from kms.catalog import Catalog
from kms.storage import ObjectStore

PARSER_NAME = 'pymupdf'
MIN_TEXT_CHARS = 40
CHUNK_TARGET_CHARS = 3200
CHUNK_MAX_CHARS = 4800
PREVIEW_CHARS = 1600
MAX_EXTRACT_CHUNKS = 8

_HEADING_RE = re.compile(
    r'^\s*(?:\d+(?:\.\d+)*\.?\s+)?'
    r'(abstract|introduction|experimental(?: section)?|materials and methods|'
    r'methods|results(?: and discussion)?|discussion|conclusions?|'
    r'references|acknowledg(?:e)?ments?|'
    r'摘要|引言|实验(?:部分)?|方法|结果与讨论|结果|讨论|结论|参考文献)'
    r'\s*$',
    re.I,
)

_SECTION_CANON = {
    'abstract': 'Abstract',
    'introduction': 'Introduction',
    'experimental': 'Experimental',
    'experimental section': 'Experimental',
    'materials and methods': 'Methods',
    'methods': 'Methods',
    'results': 'Results',
    'results and discussion': 'Results',
    'discussion': 'Discussion',
    'conclusion': 'Conclusion',
    'conclusions': 'Conclusion',
    'references': 'References',
    'acknowledgments': 'Acknowledgements',
    'acknowledgements': 'Acknowledgements',
    '摘要': 'Abstract',
    '引言': 'Introduction',
    '实验': 'Experimental',
    '实验部分': 'Experimental',
    '方法': 'Methods',
    '结果': 'Results',
    '结果与讨论': 'Results',
    '讨论': 'Discussion',
    '结论': 'Conclusion',
    '参考文献': 'References',
}


class ParseError(ValueError):
    pass


def parse_pdf_bytes(data: bytes) -> dict[str, Any]:
    if not data:
        return _empty_result('PDF 为空，无法解析')
    try:
        doc = fitz.open(stream=data, filetype='pdf')
    except Exception as exc:
        return _empty_result(f'无法打开 PDF：{exc}', status='error')
    try:
        if doc.is_encrypted:
            return _empty_result('PDF 已加密，无法解析正文', status='error')
        pages: list[dict[str, Any]] = []
        section = ''
        for index, page in enumerate(doc, start=1):
            text = (page.get_text('text') or '').replace('\x00', '')
            text = re.sub(r'[ \t]+\n', '\n', text)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()
            found = _detect_section(text)
            if found:
                section = found
            pages.append({'page': index, 'text': text, 'section': section or 'Body'})
        chunks = build_chunks(pages)
        char_count = sum(len(item['text']) for item in pages)
        preview = '\n\n'.join(
            f"[p.{item['page']}] {item['text']}" for item in pages if item['text']
        )[:PREVIEW_CHARS]
        if char_count < MIN_TEXT_CHARS:
            return {
                'status': 'empty',
                'parser': PARSER_NAME,
                'page_count': len(pages),
                'char_count': char_count,
                'chunk_count': 0,
                'preview': preview,
                'chunks': [],
                'error': '未能抽出有效正文，PDF 可能是扫描件或图片页',
            }
        return {
            'status': 'ok',
            'parser': PARSER_NAME,
            'page_count': len(pages),
            'char_count': char_count,
            'chunk_count': len(chunks),
            'preview': preview,
            'chunks': chunks,
            'error': '',
        }
    finally:
        doc.close()


def build_chunks(
    pages: list[dict[str, Any]],
    *,
    target: int = CHUNK_TARGET_CHARS,
    max_chars: int = CHUNK_MAX_CHARS,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    buf: list[str] = []
    size = 0
    page_from = 0
    page_to = 0
    section = 'Body'

    def flush() -> None:
        nonlocal buf, size, page_from, page_to, section
        text = '\n\n'.join(buf).strip()
        if not text:
            buf = []
            size = 0
            return
        chunks.append({
            'chunk_index': len(chunks),
            'section': section,
            'page_from': page_from,
            'page_to': page_to,
            'text': text,
            'char_count': len(text),
        })
        buf = []
        size = 0

    for page in pages:
        raw = (page.get('text') or '').strip()
        if not raw:
            continue
        heading = page.get('section') or 'Body'
        piece = f"[Page {page['page']} | {heading}]\n{raw}"
        if not buf:
            page_from = int(page['page'])
            section = heading
        if size and size + len(piece) > target:
            flush()
            page_from = int(page['page'])
            section = heading
        if len(piece) > max_chars:
            for part in _split_long(piece, target):
                if size and size + len(part) > target:
                    flush()
                    page_from = int(page['page'])
                    section = heading
                if not buf:
                    page_from = int(page['page'])
                    section = heading
                buf.append(part)
                size += len(part)
                page_to = int(page['page'])
            continue
        buf.append(piece)
        size += len(piece)
        page_to = int(page['page'])
        if heading and heading != section and size > target // 2:
            flush()
            section = heading
    flush()
    return chunks


def extractable_chunks(chunks: list[dict[str, Any]], limit: int = MAX_EXTRACT_CHUNKS) -> list[dict[str, Any]]:
    body = [item for item in chunks if not is_references(item.get('section') or '')]
    if not body:
        body = list(chunks)
    return body[: max(1, int(limit))]


def is_references(section: str) -> bool:
    return (section or '').strip().lower() in {'references', '参考文献'}


def ensure_document_parse(
    catalog: Catalog,
    store: ObjectStore,
    document: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    doc_id = int(document['id'])
    key = (document.get('storage_key') or '').strip()
    if not key:
        raise ParseError('该文献没有 PDF，无法解析正文')
    sha = (document.get('sha256') or '').strip()
    existing = catalog.get_parse(doc_id)
    if (
        not force
        and existing
        and existing.get('sha256') == sha
        and existing.get('status') in {'ok', 'empty'}
    ):
        return catalog.parse_payload(doc_id) or existing
    try:
        data = store.get_bytes(key)
    except FileNotFoundError as exc:
        raise ParseError('PDF 文件不在存储中，无法解析') from exc
    result = parse_pdf_bytes(data)
    catalog.save_parse(doc_id, sha, result)
    payload = catalog.parse_payload(doc_id)
    if not payload:
        raise ParseError(result.get('error') or '解析失败')
    return payload


def _detect_section(text: str) -> str:
    for line in (text or '').splitlines()[:18]:
        compact = re.sub(r'\s+', ' ', line).strip()
        if not compact or len(compact) > 48:
            continue
        match = _HEADING_RE.match(compact)
        if not match:
            continue
        key = match.group(1).lower()
        return _SECTION_CANON.get(key, match.group(1).title())
    return ''


def _split_long(text: str, target: int) -> list[str]:
    if len(text) <= target:
        return [text]
    parts: list[str] = []
    paragraphs = re.split(r'\n{2,}', text)
    buf = ''
    for para in paragraphs:
        piece = para.strip()
        if not piece:
            continue
        if buf and len(buf) + len(piece) + 2 > target:
            parts.append(buf)
            buf = piece
        else:
            buf = f'{buf}\n\n{piece}' if buf else piece
        while len(buf) > CHUNK_MAX_CHARS:
            parts.append(buf[:target])
            buf = buf[target:]
    if buf:
        parts.append(buf)
    return parts or [text[:target]]


def _empty_result(error: str, status: str = 'empty') -> dict[str, Any]:
    return {
        'status': status,
        'parser': PARSER_NAME,
        'page_count': 0,
        'char_count': 0,
        'chunk_count': 0,
        'preview': '',
        'chunks': [],
        'error': error,
    }


def make_pdf_bytes(*pages: str) -> bytes:
    """测试用：把纯文本写成可被 pymupdf 抽出的 PDF。"""
    doc = fitz.open()
    try:
        if not pages:
            pages = ('',)
        for text in pages:
            page = doc.new_page()
            rect = fitz.Rect(48, 48, 547, 780)
            page.insert_textbox(rect, text or ' ', fontsize=11)
        return doc.tobytes()
    finally:
        doc.close()
