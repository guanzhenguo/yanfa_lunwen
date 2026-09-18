# Writes UTF-8 UI files from ASCII-only unicode escapes.
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    print('wrote', path)


API = """from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from kms.catalog import Catalog, public_document
from kms.config import PROJECT_ROOT, load_settings
from kms.storage import create_store

WEB_DIST = PROJECT_ROOT / 'frontend' / 'dist'


def create_app() -> FastAPI:
    app = FastAPI(title='\u5149\u4f0f\u5b9e\u9a8c\u5ba4\u8bba\u6587\u5e93', docs_url='/api/docs')
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
        allow_methods=['*'],
        allow_headers=['*'],
    )

    def catalog() -> Catalog:
        return Catalog(load_settings().catalog_path)

    def store():
        return create_store(load_settings())

    @app.get('/api/health')
    def health():
        settings = load_settings()
        return {
            'ok': True,
            'storage': settings.storage_backend,
            'bucket': settings.minio_bucket,
        }

    @app.get('/api/stats')
    def stats():
        with catalog() as cat:
            return cat.stats()

    @app.get('/api/papers')
    def list_papers(
        q: str = '',
        doi: str = '',
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        oa: Optional[bool] = Query(default=None),
        has_pdf: Optional[bool] = Query(default=None),
        limit: int = Query(default=200, ge=1, le=500),
    ):
        with catalog() as cat:
            rows = cat.search(
                q=q,
                doi=doi,
                year_from=year_from,
                year_to=year_to,
                oa=oa,
                has_pdf=has_pdf,
                limit=limit,
            )
            return [public_document(row) for row in rows]

    @app.get('/api/papers/{doc_id}')
    def get_paper(doc_id: int):
        with catalog() as cat:
            row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='\u6587\u732e\u4e0d\u5b58\u5728')
        return public_document(row)

    @app.get('/api/papers/{doc_id}/pdf')
    def preview_pdf(doc_id: int):
        with catalog() as cat:
            row = cat.get_by_id(doc_id)
        if not row:
            raise HTTPException(status_code=404, detail='\u6587\u732e\u4e0d\u5b58\u5728')
        key = row.get('storage_key') or ''
        if not key:
            raise HTTPException(status_code=404, detail='\u8fd9\u7bc7\u8fd8\u6ca1\u6709\u5165\u5e93 PDF')
        try:
            data = store().get_bytes(key)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        filename = (row.get('doi') or f'paper-{doc_id}').replace('/', '_') + '.pdf'
        quoted = quote(filename)
        return Response(
            content=data,
            media_type='application/pdf',
            headers={
                'Content-Disposition': f"inline; filename*=UTF-8''{quoted}",
                'Cache-Control': 'private, max-age=120',
                'X-Content-Type-Options': 'nosniff',
            },
        )

    if WEB_DIST.is_dir():
        app.mount('/', StaticFiles(directory=WEB_DIST, html=True), name='web')

    return app


app = create_app()
"""

APP_VUE = """<script setup>
import { computed, onMounted, ref, watch } from 'vue'

const keyword = ref('')
const doi = ref('')
const yearFrom = ref('')
const yearTo = ref('')
const oa = ref('all')
const pdf = ref('all')
const stats = ref({ total: 0, oa: 0, with_pdf: 0 })
const papers = ref([])
const selectedId = ref(null)
const loading = ref(false)
const error = ref('')

const selected = computed(
  () => papers.value.find((item) => item.id === selectedId.value) || null,
)

const pdfUrl = computed(() => {
  if (!selected.value?.has_pdf) return ''
  return `/api/papers/${selected.value.id}/pdf`
})

function boolParam(value) {
  if (value === 'yes') return true
  if (value === 'no') return false
  return undefined
}

async function loadStats() {
  const res = await fetch('/api/stats')
  stats.value = await res.json()
}

async function loadPapers() {
  loading.value = true
  error.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('q', keyword.value.trim())
  if (doi.value.trim()) params.set('doi', doi.value.trim())
  if (yearFrom.value) params.set('year_from', yearFrom.value)
  if (yearTo.value) params.set('year_to', yearTo.value)
  const oaVal = boolParam(oa.value)
  const pdfVal = boolParam(pdf.value)
  if (oaVal !== undefined) params.set('oa', String(oaVal))
  if (pdfVal !== undefined) params.set('has_pdf', String(pdfVal))
  try {
    const res = await fetch(`/api/papers?${params.toString()}`)
    if (!res.ok) throw new Error('\u68c0\u7d22\u5931\u8d25')
    papers.value = await res.json()
    if (!papers.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = papers.value[0]?.id ?? null
    }
  } catch (err) {
    error.value = err.message || '\u68c0\u7d22\u5931\u8d25'
  } finally {
    loading.value = false
  }
}

let timer = 0
watch([keyword, doi, yearFrom, yearTo, oa, pdf], () => {
  window.clearTimeout(timer)
  timer = window.setTimeout(loadPapers, 220)
})

onMounted(async () => {
  await loadStats()
  await loadPapers()
})
</script>

<template>
  <div class="shell">
    <header class="masthead">
      <div class="brand">
        <h1>\u5149\u4f0f\u5b9e\u9a8c\u5ba4\u8bba\u6587\u5e93</h1>
        <p>Springer \u5165\u5e93\u6587\u732e \u00b7 \u70b9\u9009\u5de6\u4fa7\u5373\u53ef\u9884\u89c8 PDF</p>
      </div>
      <div class="search">
        <input v-model="keyword" type="search" placeholder="\u9898\u540d\u3001\u4f5c\u8005\u3001\u6458\u8981" />
        <input v-model="doi" type="search" placeholder="DOI" />
        <input v-model="yearFrom" class="year" type="number" placeholder="\u8d77\u59cb\u5e74" />
        <input v-model="yearTo" class="year" type="number" placeholder="\u7ed3\u675f\u5e74" />
        <div class="chips">
          <button class="chip" :class="{ active: oa === 'all' && pdf === 'all' }" @click="oa = 'all'; pdf = 'all'">\u5168\u90e8</button>
          <button class="chip" :class="{ active: oa === 'yes' }" @click="oa = 'yes'">OA</button>
          <button class="chip" :class="{ active: pdf === 'yes' }" @click="pdf = 'yes'">\u6709 PDF</button>
        </div>
      </div>
    </header>

    <main class="workspace">
      <aside class="rail">
        <div class="rail-meta">
          \u9986\u85cf {{ stats.total }} \u00b7 OA {{ stats.oa }} \u00b7 PDF {{ stats.with_pdf }}
          \u00b7 \u672c\u6b21 {{ papers.length }}
        </div>
        <div class="list">
          <p v-if="error" class="hint">{{ error }}</p>
          <p v-else-if="loading && !papers.length" class="hint">\u6b63\u5728\u68c0\u7d22\u2026</p>
          <p v-else-if="!papers.length" class="hint">
            \u6ca1\u6709\u547d\u4e2d\u3002\u5148\u8fd0\u884c\u91c7\u96c6\u5165\u5e93\uff0c\u6216\u653e\u5bbd\u7b5b\u9009\u3002
          </p>
          <button
            v-for="item in papers"
            :key="item.id"
            class="card"
            :class="{ selected: item.id === selectedId }"
            @click="selectedId = item.id"
          >
            <h2>{{ item.title || '\u672a\u547d\u540d\u6587\u732e' }}</h2>
            <div class="meta">
              <span>{{ item.year || item.published || '\u5e74\u4efd\u672a\u77e5' }}</span>
              <span>{{ item.authors || '\u4f5c\u8005\u672a\u77e5' }}</span>
              <span v-if="item.open_access" class="badge oa">OA</span>
              <span v-if="item.has_pdf" class="badge pdf">PDF</span>
            </div>
          </button>
        </div>
      </aside>

      <section class="stage">
        <div v-if="selected" class="stage-bar">
          <div>
            <h2>{{ selected.title }}</h2>
            <div class="meta">
              <span>{{ selected.authors || '\u4f5c\u8005\u672a\u77e5' }}</span>
              <span>{{ selected.published || selected.year || '' }}</span>
              <span v-if="selected.doi">DOI {{ selected.doi }}</span>
              <span>{{ selected.parent }}</span>
            </div>
            <p v-if="selected.description" class="abstract">{{ selected.description }}</p>
          </div>
          <div class="actions">
            <a v-if="selected.has_pdf" :href="pdfUrl" target="_blank" rel="noreferrer">\u65b0\u7a97\u53e3\u6253\u5f00</a>
            <a v-if="selected.has_pdf" :href="pdfUrl" download>\u4e0b\u8f7d</a>
            <a v-if="selected.url" :href="selected.url" target="_blank" rel="noreferrer">Springer</a>
          </div>
        </div>
        <div class="preview">
          <iframe
            v-if="selected && selected.has_pdf"
            :src="pdfUrl"
            title="PDF \u9884\u89c8"
          />
          <p v-else-if="selected" class="empty">\u8fd9\u7bc7\u8fd8\u6ca1\u6709\u5165\u5e93 PDF\u3002\u5bf9 OA \u6587\u732e\u91cd\u65b0\u91c7\u96c6\u5e76\u52a0\u4e0a --download-pdf\u3002</p>
          <p v-else class="empty">\u4ece\u5de6\u4fa7\u9009\u62e9\u4e00\u7bc7\u8bba\u6587\u540e\uff0c\u8fd9\u91cc\u9884\u89c8 PDF\u3002</p>
        </div>
      </section>
    </main>
  </div>
</template>
"""

INDEX = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>\u5149\u4f0f\u5b9e\u9a8c\u5ba4\u8bba\u6587\u5e93</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
"""


if __name__ == '__main__':
    write('kms/api.py', API)
    write('frontend/src/App.vue', APP_VUE)
    write('frontend/index.html', INDEX)
