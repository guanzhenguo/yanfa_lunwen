from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

_SPRINGER_DOI_RE = re.compile(
    r'/(?:article|chapter|book|protocol|referenceworkentry|datacitedetails)/'
    r'(\d{2}\.\d{4}/[^?#]+)$',
    re.I,
)
_GENERIC_DOI_RE = re.compile(r'(10\.\d{4,9}/[^\s\"<>]+)', re.I)


def doi_from_url(url: str) -> str:
    """从 Springer 详情 URL 或通用 DOI 链接中取出 DOI。"""
    if not url:
        return ''
    path = unquote(urlparse(url).path).rstrip('/')
    match = _SPRINGER_DOI_RE.search(path)
    if match:
        return _clean_doi(match.group(1))
    generic = _GENERIC_DOI_RE.search(unquote(url))
    if generic:
        return _clean_doi(generic.group(1))
    return ''


def _clean_doi(doi: str) -> str:
    doi = doi.strip().rstrip('/')
    doi = re.sub(r'\.pdf$', '', doi, flags=re.I)
    return doi
