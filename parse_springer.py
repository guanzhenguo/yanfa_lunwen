'''
访问 Springer Nature 搜索页并解析结果。
对 open_access 文章可进一步访问详情页，找到 Download PDF 并下载。
PDF 写入对象存储（本地目录模拟 MinIO），元数据写入 SQLite 文献库。
示例：https://link.springer.com/search?query=Perovskite&sortBy=relevance&page=2
'''
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests

from kms.catalog import Catalog
from kms.config import load_settings
from kms.doi import doi_from_url
from kms.keywords import KeywordStore
from kms.storage import create_store, object_key, sha256_file

# Windows 控制台避免特殊字符打印报错
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = 'https://link.springer.com'
SEARCH_URL = f'{BASE_URL}/search'

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

CSV_FIELDS = [
    'doi', 'title', 'url', 'content_type', 'authors',
    'published', 'parent', 'description', 'open_access',
    'pdf_url', 'storage_key', 'sha256', 'pdf_path',
]


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_search_page(
    session: requests.Session,
    query: str,
    page: int = 1,
    sort_by: str = 'relevance',
    retries: int = 3,
) -> str:
    params = {
        'query': query,
        'sortBy': sort_by,
        'page': page,
    }
    url = f'{SEARCH_URL}?{urlencode(params)}'
    print(f'Fetching: {url}')

    last_error = None
    for attempt in range(1, retries + 1):
        resp = session.get(
            url,
            timeout=30,
            headers={'Referer': BASE_URL + '/'},
        )
        resp.raise_for_status()
        if 'data-test="search-result-item"' in resp.text:
            return resp.text

        last_error = (
            '页面未包含搜索结果，可能触发了反爬验证。'
            '可稍后重试，或把 HTML 保存后用 --html-file 解析。'
        )
        wait = attempt * 2
        print(f'  Attempt {attempt}/{retries} blocked, retry in {wait}s...')
        time.sleep(wait)

    raise RuntimeError(last_error)


def _clean_text(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_articles(html: str) -> list:
    articles = html.split('data-test="search-result-item"')
    results = []

    for article in articles[1:]:
        title_match = re.search(
            r'app-card-open__heading.*?data-test="title".*?'
            r'<a[^>]*href="([^"]+)"[^>]*>\s*(?:<span>)?(.*?)</(?:span|a)>',
            article,
            re.DOTALL,
        )
        if title_match:
            path = title_match.group(1)
            title = _clean_text(title_match.group(2))
        else:
            fallback = re.search(
                r'app-card-open__heading.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                article,
                re.DOTALL,
            )
            if not fallback:
                continue
            path = fallback.group(1)
            title = _clean_text(fallback.group(2))

        content_type_match = re.search(
            r'data-test="content-type".*?<span[^>]*>(.*?)</span>',
            article,
            re.DOTALL,
        )
        authors_match = re.search(r'data-test="authors">(.*?)</span>', article, re.DOTALL)
        published_match = re.search(r'data-test="published">(.*?)</span>', article, re.DOTALL)
        desc_match = re.search(
            r'data-test="description">(.*?)</div>',
            article,
            re.DOTALL,
        )
        parent_match = re.search(
            r'data-test="parent"[^>]*>(.*?)</a>',
            article,
            re.DOTALL,
        )

        is_oa = 'data-test="oa-label"' in article
        url = urljoin(BASE_URL, path)

        results.append({
            'doi': doi_from_url(url),
            'title': title,
            'url': url,
            'content_type': _clean_text(content_type_match.group(1)) if content_type_match else '',
            'authors': _clean_text(authors_match.group(1)) if authors_match else '',
            'published': _clean_text(published_match.group(1)) if published_match else '',
            'parent': _clean_text(parent_match.group(1)) if parent_match else '',
            'description': _clean_text(desc_match.group(1)) if desc_match else '',
            'open_access': is_oa,
            'source': 'springer',
            'pdf_url': '',
            'pdf_path': '',
            'storage_key': '',
            'sha256': '',
        })

    return results


def extract_pdf_url(html: str, article_url: str) -> str:
    """从文章详情页提取 Download PDF 链接。"""
    patterns = [
        r'<a[^>]*data-test="pdf-link"[^>]*href="([^"]+)"',
        r'<a[^>]*class="[^"]*c-pdf-download__link[^"]*"[^>]*href="([^"]+)"',
        r'<a[^>]*href="([^"]+)"[^>]*data-test="pdf-link"',
        r'<a[^>]*href="([^"]+)"[^>]*data-track-action="download pdf"',
        r'href="(/content/pdf/[^"]+\.pdf)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I | re.DOTALL)
        if match:
            return urljoin(article_url, match.group(1))
    return ''


def _fill_from_existing(article: dict, existing: dict, store) -> bool:
    sha256 = existing.get('sha256') or ''
    key = existing.get('storage_key') or (object_key(sha256) if sha256 else '')
    if not key or not store.exists(key):
        return False
    article['doi'] = article.get('doi') or existing.get('doi') or ''
    article['storage_key'] = key
    article['sha256'] = sha256
    article['pdf_url'] = article.get('pdf_url') or existing.get('pdf_url') or ''
    article['pdf_path'] = existing.get('file_location') or store.location(key)
    return True


def download_pdf(
    session: requests.Session,
    article: dict,
    store,
    catalog: Catalog,
    delay: float = 1.0,
) -> str:
    """访问 OA 文章页，下载 PDF 到对象存储并更新文献库。"""
    article['doi'] = article.get('doi') or doi_from_url(article['url'])
    existing = catalog.get_existing(article['doi'], article['url'])
    if existing and _fill_from_existing(article, existing, store):
        print(f'  Skip existing object: {article["storage_key"]}')
        catalog.upsert_document(article)
        return article['pdf_path']

    article_url = article['url']
    print(f'  Opening OA article: {article_url}')
    resp = session.get(article_url, timeout=30)
    resp.raise_for_status()

    pdf_url = extract_pdf_url(resp.text, article_url)
    if not pdf_url:
        print('  WARNING: Download PDF button not found')
        catalog.upsert_document(article)
        return ''

    article['pdf_url'] = pdf_url
    print(f'  PDF URL: {pdf_url}')
    time.sleep(delay)

    pdf_resp = session.get(
        pdf_url,
        timeout=120,
        headers={'Accept': 'application/pdf,*/*'},
        stream=True,
    )
    pdf_resp.raise_for_status()

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp_path = tmp.name
            first_chunk = next(pdf_resp.iter_content(chunk_size=8192), b'')
            content_type = (pdf_resp.headers.get('Content-Type') or '').lower()
            if 'pdf' not in content_type and not first_chunk.startswith(b'%PDF'):
                print(f'  WARNING: Not a PDF response ({content_type})')
                return ''
            tmp.write(first_chunk)
            for chunk in pdf_resp.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)

        sha256 = sha256_file(tmp_path)
        key = object_key(sha256)
        location = store.put_file(key, Path(tmp_path))
        article['sha256'] = sha256
        article['storage_key'] = key
        article['pdf_path'] = location
        catalog.upsert_document(article)
        size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
        print(f'  Stored: {key} ({size_mb:.2f} MB)')
        print(f'  Location: {location}')
        return location
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def download_open_access_pdfs(
    session: requests.Session,
    results: list,
    store,
    catalog: Catalog,
    delay: float = 1.0,
) -> None:
    oa_items = [item for item in results if item.get('open_access')]
    print(f'\nOpen Access articles to download: {len(oa_items)}')
    if not oa_items:
        return

    for i, item in enumerate(oa_items, 1):
        print(f'\n[{i}/{len(oa_items)}] {item["title"]}')
        try:
            download_pdf(session, item, store=store, catalog=catalog, delay=delay)
        except Exception as exc:
            print(f'  ERROR: {exc}')
            catalog.upsert_document(item)
        if i < len(oa_items):
            time.sleep(delay)


def print_results(results: list) -> None:
    print(f'Total articles: {len(results)}')
    print()
    for i, item in enumerate(results, 1):
        oa_marker = ' [OPEN ACCESS]' if item['open_access'] else ''
        ctype = f" ({item['content_type']})" if item['content_type'] else ''
        print(f'{i}. {item["title"]}{ctype}{oa_marker}')
        if item.get('doi'):
            print(f'   DOI: {item["doi"]}')
        print(f'   URL: {item["url"]}')
        if item['authors']:
            print(f'   Authors: {item["authors"]}')
        if item['published']:
            print(f'   Published: {item["published"]}')
        if item['parent']:
            print(f'   In: {item["parent"]}')
        if item.get('storage_key'):
            print(f'   Object: {item["storage_key"]}')
        if item.get('pdf_path'):
            print(f'   PDF: {item["pdf_path"]}')
        print()


def save_results(results: list, output: str) -> None:
    rows = []
    for item in results:
        rows.append({field: item.get(field, '') for field in CSV_FIELDS})

    if output.lower().endswith('.json'):
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    elif output.lower().endswith('.csv'):
        with open(output, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    else:
        raise ValueError('输出文件仅支持 .json 或 .csv')
    print(f'Saved {len(results)} records to {output}')


def main() -> None:
    parser = argparse.ArgumentParser(description='解析 Springer Nature 搜索结果并入库')
    parser.add_argument('-q', '--query', default='Perovskite', help='搜索关键词')
    parser.add_argument('-p', '--page', type=int, default=1, help='页码，从 1 开始')
    parser.add_argument('--sort-by', default='relevance', help='排序方式，默认 relevance')
    parser.add_argument('--pages', type=int, default=3, help='连续抓取页数，默认 3 页')
    parser.add_argument('--html-file', help='跳过网络请求，直接解析本地 HTML 文件')
    parser.add_argument('-o', '--output', help='额外保存结果到 .json 或 .csv')
    parser.add_argument(
        '--download-pdf',
        action='store_true',
        help='对 open_access=True 的条目访问详情页并下载 PDF',
    )
    parser.add_argument(
        '--pdf-dir',
        default=None,
        help='兼容旧参数：作为本地模拟 MinIO 的根目录（其下 papers/）',
    )
    parser.add_argument(
        '--storage-root',
        default=None,
        help='本地模拟 MinIO 根目录，默认 data/minio',
    )
    parser.add_argument(
        '--catalog',
        default=None,
        help='SQLite 文献库路径，默认 data/catalog.sqlite',
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='下载间隔秒数，默认 1.0',
    )
    args = parser.parse_args()

    settings = load_settings(
        storage_root=args.storage_root or args.pdf_dir,
        catalog_path=args.catalog,
    )
    store = create_store(settings)
    print(f'Storage: {store.backend} bucket={store.bucket}')
    if store.backend == 'local':
        print(f'  Root: {settings.local_root}')
    print(f'Catalog: {settings.catalog_path}')

    session = create_session()
    all_results = []
    query_label = args.query if not args.html_file else f'html:{args.html_file}'

    with Catalog(settings.catalog_path) as catalog:
        keywords = KeywordStore(catalog)
        job_id = catalog.start_job(query_label, args.page, args.pages)
        error = ''
        try:
            if args.html_file:
                with open(args.html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    html = f.read()
                all_results.extend(parse_articles(html))
            else:
                for offset in range(args.pages):
                    page = args.page + offset
                    html = fetch_search_page(session, args.query, page=page, sort_by=args.sort_by)
                    page_results = parse_articles(html)
                    print(f'Page {page}: {len(page_results)} items')
                    all_results.extend(page_results)

            bind_query = args.query if not args.html_file else ''
            for item in all_results:
                doc_id = catalog.upsert_document(item)
                if bind_query:
                    keywords.add_document_keywords(doc_id, [bind_query], source='ingest')

            print_results(all_results)

            if args.download_pdf:
                download_open_access_pdfs(
                    session,
                    all_results,
                    store=store,
                    catalog=catalog,
                    delay=args.delay,
                )
                saved = [r for r in all_results if r.get('storage_key')]
                print(f'\nStored PDFs: {len(saved)}')

            catalog.finish_job(
                job_id,
                status='done',
                item_count=len(all_results),
                downloaded_count=sum(1 for r in all_results if r.get('storage_key')),
            )
        except Exception as exc:
            error = str(exc)
            catalog.finish_job(
                job_id,
                status='error',
                item_count=len(all_results),
                downloaded_count=sum(1 for r in all_results if r.get('storage_key')),
                error=error,
            )
            raise

    if args.output:
        save_results(all_results, args.output)


if __name__ == '__main__':
    main()
