<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import ChatPage from './ChatPage.vue'
import GraphChart from './GraphChart.vue'

const page = ref('papers')
const me = ref(null)
const loginUser = ref('admin')
const loginPass = ref('')
const loginError = ref('')
const keyword = ref('')
const topicId = ref(null)
const topics = ref([])
const doi = ref('')
const yearFrom = ref('')
const yearTo = ref('')
const oa = ref('all')
const pdf = ref('all')
const stats = ref({ total: 0, oa: 0, with_pdf: 0 })
const papers = ref([])
const loading = ref(false)
const error = ref('')
const previewId = ref(null)
const upload = ref({
  title: '',
  authors: '',
  doi: '',
  year: '',
  description: '',
  keywords: '',
  file: null,
})
const uploadMsg = ref('')
const parsing = ref(false)
const users = ref([])
const newUser = ref({ username: '', password: '', role: 'user' })
const userMsg = ref('')
const settings = ref({
  ai: { base_url: '', model: '', api_key: '', timeout_seconds: 90, ready: false, api_key_set: false },
  neo4j: { enabled: false, uri: '', user: '', password: '', database: 'neo4j' },
})
const prompts = ref([])
const settingsMsg = ref('')
const graphPaper = ref(null)
const graphData = ref({ run: null, nodes: [], edges: [], parse: null })
const parseInfo = ref(emptyParse())
const extractPromptBody = ref('')
const savedDefaultPrompt = ref('')
const extractDefaultSchema = ref('')
const extractKeywords = ref([])
const graphLang = ref('zh')
const graphMsg = ref('')
const extracting = ref(false)
const translating = ref(false)
const parsingPdf = ref(false)
const promptSaving = ref(false)
const reviewNote = ref('')
const editKw = ref({ id: null, title: '', text: '' })
const previewUrl = computed(() =>
  previewId.value ? `/api/papers/${previewId.value}/pdf` : '',
)

function api(path, options = {}) {
  return fetch(path, { credentials: 'include', ...options })
}

function boolParam(value) {
  if (value === 'yes') return true
  if (value === 'no') return false
  return undefined
}

function statusLabel(status) {
  return (
    {
      pending_review: '待审核',
      approved: '已通过',
      rejected: '已驳回',
      error: '抽取失败',
    }[status] || '未抽取'
  )
}

function promptLabel(name) {
  return (
    {
      metadata_parse: '上传元数据解析',
      knowledge_extract: '知识图谱抽取',
      knowledge_localize: '图谱中文化',
      knowledge_qa: '文献问答',
    }[name] || name
  )
}

function formatKeywords(items) {
  return (items || []).map((item) => item.name || item).join(', ')
}

function emptyParse() {
  return {
    status: 'none',
    page_count: 0,
    char_count: 0,
    chunk_count: 0,
    preview: '',
    error: '',
    has_pdf: false,
    chunks: [],
  }
}

const parseChunks = computed(() => parseInfo.value.chunks || [])
const chartNodes = computed(() =>
  (graphData.value.nodes || []).map((node) => ({
    ...node,
    label: graphLang.value === 'zh' ? node.label_zh || node.label : node.label,
  })),
)
const chartEdges = computed(() =>
  (graphData.value.edges || []).map((edge) => ({
    ...edge,
    rel_type: graphLang.value === 'zh' ? edge.rel_type_zh || edge.rel_type : edge.rel_type,
  })),
)
const settingsPrompts = computed(() =>
  (prompts.value || []).filter(
    (item) => item.name !== 'knowledge_extract' && item.name !== 'knowledge_localize',
  ),
)

function applyExtractConfig(cfg) {
  const config = cfg || {}
  const defaultPrompt = config.default_prompt || ''
  savedDefaultPrompt.value = defaultPrompt
  extractPromptBody.value = defaultPrompt
  extractDefaultSchema.value = config.default_schema || ''
  extractKeywords.value = (config.keywords || []).map((item) => ({
    id: item.id,
    name: item.name,
    paper_count: item.paper_count,
    extract_prompt: (item.extract_prompt || '').trim() || defaultPrompt,
    extract_schema: item.extract_schema || '',
    has_custom_prompt: Boolean(item.has_custom_prompt),
    has_custom_schema: Boolean(item.has_custom_schema),
  }))
}

function keywordPromptPayload(item) {
  const current = (item.extract_prompt || '').trim()
  const shared = (extractPromptBody.value || savedDefaultPrompt.value || '').trim()
  return current && current !== shared ? current : ''
}

function parseStatusLabel(status) {
  return (
    {
      none: '未解析',
      ok: '已解析',
      empty: '无正文',
      error: '解析失败',
    }[status] || '未解析'
  )
}

function emptyUpload() {
  return { title: '', authors: '', doi: '', year: '', description: '', keywords: '', file: null }
}

async function loadMe() {
  const res = await api('/api/auth/me')
  if (res.ok) {
    me.value = await res.json()
    return true
  }
  me.value = null
  return false
}

async function doLogin() {
  loginError.value = ''
  const res = await api('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: loginUser.value,
      password: loginPass.value,
    }),
  })
  if (!res.ok) {
    loginError.value = '用户名或密码错误'
    return
  }
  me.value = await res.json()
  loginPass.value = ''
  page.value = 'papers'
  await loadStats()
  await loadPapers()
  await loadSettings()
}

async function doLogout() {
  await api('/api/auth/logout', { method: 'POST' })
  me.value = null
  papers.value = []
  users.value = []
  topics.value = []
  previewId.value = null
  graphPaper.value = null
}

async function loadStats() {
  const res = await api('/api/stats')
  if (res.ok) stats.value = await res.json()
}

async function loadPapers() {
  loading.value = true
  error.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('q', keyword.value.trim())
  if (topicId.value) params.set('keyword_id', String(topicId.value))
  if (doi.value.trim()) params.set('doi', doi.value.trim())
  if (yearFrom.value) params.set('year_from', yearFrom.value)
  if (yearTo.value) params.set('year_to', yearTo.value)
  const oaVal = boolParam(oa.value)
  const pdfVal = boolParam(pdf.value)
  if (oaVal !== undefined) params.set('oa', String(oaVal))
  if (pdfVal !== undefined) params.set('has_pdf', String(pdfVal))
  try {
    const res = await api(`/api/papers?${params.toString()}`)
    if (res.status === 401) {
      me.value = null
      return
    }
    if (!res.ok) throw new Error('检索失败')
    papers.value = await res.json()
  } catch (err) {
    error.value = err.message || '检索失败'
  } finally {
    loading.value = false
  }
}

async function loadKeywords() {
  const res = await api('/api/keywords')
  if (res.ok) topics.value = await res.json()
}

async function loadUsers() {
  const res = await api('/api/users')
  if (res.ok) users.value = await res.json()
}

async function loadSettings() {
  const res = await api('/api/settings')
  if (res.ok) settings.value = await res.json()
  const promptRes = await api('/api/kg/prompts')
  if (promptRes.ok) prompts.value = await promptRes.json()
  await loadKeywords()
}

async function saveAi() {
  settingsMsg.value = ''
  const res = await api('/api/settings/ai', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings.value.ai),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    settingsMsg.value = body.detail || '无法保存 AI 配置'
    return
  }
  settings.value.ai = body
  settingsMsg.value = 'AI 配置已写入 config.toml'
}

async function saveNeo4j() {
  settingsMsg.value = ''
  const res = await api('/api/settings/neo4j', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings.value.neo4j),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    settingsMsg.value = body.detail || '无法保存 Neo4j 配置'
    return
  }
  settings.value.neo4j = body
  settingsMsg.value = 'Neo4j 配置已写入 config.toml，同步尚未启用'
}

async function savePrompt(item) {
  settingsMsg.value = ''
  const res = await api(`/api/kg/prompts/${item.name}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body: item.body }),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    settingsMsg.value = body.detail || '无法保存提示词'
    return
  }
  settingsMsg.value = `已保存提示词：${promptLabel(item.name)}`
  await loadSettings()
}

async function saveKeywordPrompt(item) {
  settingsMsg.value = ''
  const payload = { name: item.name }
  const res = await api(`/api/keywords/${item.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    settingsMsg.value = body.detail || '无法保存关键词'
    return
  }
  settingsMsg.value = `已保存关键词：${item.name}`
  await loadKeywords()
}

async function saveGraphExtractPrompt() {
  graphMsg.value = ''
  promptSaving.value = true
  try {
    const res = await api('/api/kg/prompts/knowledge_extract', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body: extractPromptBody.value }),
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      graphMsg.value = body.detail || '无法保存默认图谱提示词'
      return false
    }
    savedDefaultPrompt.value = body.body || extractPromptBody.value
    extractPromptBody.value = savedDefaultPrompt.value
    extractKeywords.value.forEach((item) => {
      if (!item.has_custom_prompt) item.extract_prompt = savedDefaultPrompt.value
    })
    graphMsg.value = '已保存默认图谱提示词，未自定义的关键词将共用这条'
    await loadSettings()
    return true
  } finally {
    promptSaving.value = false
  }
}

async function saveGraphKeyword(item) {
  graphMsg.value = ''
  promptSaving.value = true
  try {
    const payload = {
      name: item.name,
      extract_prompt: keywordPromptPayload(item),
      extract_schema: item.extract_schema || '',
    }
    const res = await api(`/api/keywords/${item.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      graphMsg.value = body.detail || '无法保存关键词抽取设置'
      return false
    }
    item.has_custom_prompt = Boolean(body.has_custom_prompt)
    item.has_custom_schema = Boolean(body.has_custom_schema)
    item.extract_prompt = (body.extract_prompt || '').trim() || extractPromptBody.value
    item.extract_schema = body.extract_schema || ''
    graphMsg.value = `已保存「${item.name}」的提示词 / schema`
    await loadKeywords()
    return true
  } finally {
    promptSaving.value = false
  }
}

function resetKeywordPrompt(item) {
  item.extract_prompt = extractPromptBody.value
  item.has_custom_prompt = false
}

async function createUser() {
  userMsg.value = ''
  const res = await api('/api/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(newUser.value),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    userMsg.value = body.detail || '无法创建用户'
    return
  }
  newUser.value = { username: '', password: '', role: 'user' }
  await loadUsers()
}

async function toggleUser(user) {
  await api(`/api/users/${user.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active: !user.active }),
  })
  await loadUsers()
}

function onFile(event) {
  const file = event.target.files?.[0] || null
  upload.value.file = file
  if (file && !upload.value.title.trim()) {
    upload.value.title = file.name.replace(/\.pdf$/i, '').replace(/[_-]+/g, ' ')
  }
}

async function parseUpload() {
  uploadMsg.value = ''
  if (!upload.value.file && !upload.value.title) {
    uploadMsg.value = '请先选择 PDF，或填写题名后再解析'
    return
  }
  parsing.value = true
  const data = new FormData()
  data.append('title', upload.value.title)
  data.append('authors', upload.value.authors)
  data.append('doi', upload.value.doi)
  data.append('year', upload.value.year)
  data.append('description', upload.value.description)
  data.append('keywords', upload.value.keywords)
  data.append('filename', upload.value.file?.name || '')
  if (upload.value.file) data.append('file', upload.value.file)
  try {
    const res = await api('/api/papers/parse-metadata', { method: 'POST', body: data })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      uploadMsg.value = body.detail || '解析失败'
      return
    }
    upload.value.title = body.title || upload.value.title
    upload.value.authors = body.authors || upload.value.authors
    upload.value.doi = body.doi || upload.value.doi
    upload.value.year = body.year || upload.value.year
    upload.value.description = body.description || upload.value.description
    if (Array.isArray(body.keywords) && body.keywords.length) {
      upload.value.keywords = body.keywords.join(', ')
    }
    if (body.ai_used) {
      uploadMsg.value = '已用 AI 填入，请核对后保存'
    } else if (body.ai_error) {
      uploadMsg.value = `AI 不可用，已按文件名填入。${body.ai_error}`
    } else {
      uploadMsg.value = '当前未配置 AI，已按文件名填入题名，其余字段请手工补充'
    }
  } finally {
    parsing.value = false
  }
}

async function submitUpload() {
  uploadMsg.value = ''
  if (!upload.value.file) {
    uploadMsg.value = '请先选择 PDF'
    return
  }
  const data = new FormData()
  data.append('title', upload.value.title)
  data.append('authors', upload.value.authors)
  data.append('doi', upload.value.doi)
  data.append('year', upload.value.year)
  data.append('description', upload.value.description)
  data.append('keywords', upload.value.keywords)
  data.append('file', upload.value.file)
  const res = await api('/api/papers/upload', { method: 'POST', body: data })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    uploadMsg.value = body.detail || '上传失败'
    return
  }
  upload.value = emptyUpload()
  uploadMsg.value = '上传成功'
  await loadStats()
  await loadKeywords()
}

function openPreview(id) {
  previewId.value = id
}

function closePreview() {
  previewId.value = null
}

function openEditKeywords(item) {
  editKw.value = {
    id: item.id,
    title: item.title,
    text: formatKeywords(item.keywords),
  }
}

function closeEditKeywords() {
  editKw.value = { id: null, title: '', text: '' }
}

async function savePaperKeywords() {
  if (!editKw.value.id) return
  const res = await api(`/api/papers/${editKw.value.id}/keywords`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords: editKw.value.text }),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    error.value = body.detail || '无法更新论文关键词'
    return
  }
  closeEditKeywords()
  await loadPapers()
  await loadKeywords()
}

function setTopic(id) {
  topicId.value = topicId.value === id ? null : id
}

async function openGraph(item) {
  graphPaper.value = item
  graphMsg.value = ''
  reviewNote.value = ''
  graphLang.value = 'zh'
  parseInfo.value = emptyParse()
  const res = await api(`/api/papers/${item.id}/kg`)
  graphData.value = res.ok
    ? await res.json()
    : { run: null, nodes: [], edges: [], parse: null }
  if (graphData.value.parse) parseInfo.value = graphData.value.parse
  applyExtractConfig(graphData.value.extract)
  const needAi = Boolean(
    settings.value.ai?.ready
    && graphData.value.nodes?.length
    && graphData.value.run?.zh_status !== 'ai',
  )
  if (needAi) {
    await translateGraph(true)
  }
}

function closeGraph() {
  graphPaper.value = null
  graphData.value = { run: null, nodes: [], edges: [], parse: null }
  parseInfo.value = emptyParse()
  extractPromptBody.value = ''
  savedDefaultPrompt.value = ''
  extractDefaultSchema.value = ''
  extractKeywords.value = []
}

async function parsePaper(force = false) {
  if (!graphPaper.value) return
  parsingPdf.value = true
  graphMsg.value = ''
  try {
    const suffix = force ? '?force=true' : ''
    const res = await api(`/api/papers/${graphPaper.value.id}/parse${suffix}`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      graphMsg.value = body.detail || '解析失败'
      return
    }
    parseInfo.value = body
    if (body.status === 'ok') {
      graphMsg.value = `已解析 ${body.page_count} 页、${body.chunk_count} 块正文`
    } else {
      graphMsg.value = body.error || '未能抽出正文'
    }
  } finally {
    parsingPdf.value = false
  }
}

async function extractGraph() {
  if (!graphPaper.value) return
  extracting.value = true
  graphMsg.value = ''
  try {
    const res = await api(`/api/papers/${graphPaper.value.id}/kg/extract`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      graphMsg.value = body.detail || '抽取失败'
      if (body.parse) parseInfo.value = body.parse
      return
    }
    graphData.value = body
    if (body.parse) parseInfo.value = body.parse
    if (body.extract) applyExtractConfig(body.extract)
    if (body.run?.error) {
      graphMsg.value = `部分抽取失败，已保留系统属性与已抽出内容，请审核。${body.run.error}`
    } else {
      graphMsg.value = '抽取完成。中文图谱由已有节点翻译而来，请审核后再通过'
    }
  } finally {
    extracting.value = false
  }
}

async function translateGraph(auto = false) {
  if (!graphPaper.value || translating.value) return
  translating.value = true
  graphMsg.value = auto
    ? '正在把已有图谱译成中文，无需重新抽取...'
    : '正在把现有图谱译成中文...'
  try {
    const res = await api(`/api/papers/${graphPaper.value.id}/kg/translate`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      graphMsg.value = body.detail || '翻译失败'
      return
    }
    graphData.value = body
    if (body.parse) parseInfo.value = body.parse
    if (body.extract) applyExtractConfig(body.extract)
    graphLang.value = 'zh'
    if (body.zh_error) {
      graphMsg.value = `已译出中文类型和关系；模型翻译未完成。${body.zh_error}`
    } else {
      graphMsg.value = '已根据现有图谱翻译成中文，未重新抽取'
    }
  } finally {
    translating.value = false
  }
}

async function reviewGraph(status) {
  const runId = graphData.value.run?.id
  if (!runId) return
  const res = await api(`/api/kg/runs/${runId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, note: reviewNote.value }),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    graphMsg.value = body.detail || '审核失败'
    return
  }
  graphData.value = body
  graphMsg.value = status === 'approved' ? '已通过，可待后续同步 Neo4j' : '已驳回'
}

watch([keyword, topicId, doi, yearFrom, yearTo, oa, pdf], () => {
  if (!me.value) return
  window.clearTimeout(openPreview._t)
  openPreview._t = window.setTimeout(loadPapers, 220)
})

watch(page, async (value) => {
  if (value === 'users' && me.value?.role === 'admin') await loadUsers()
  if (value === 'settings') await loadSettings()
})

onMounted(async () => {
  if (await loadMe()) {
    await loadStats()
    await loadPapers()
    await loadKeywords()
    await loadSettings()
  }
})
</script>

<template>
  <div v-if="!me" class="login-wrap">
    <form class="login-card" @submit.prevent="doLogin">
      <div class="login-mark" aria-hidden="true">PV</div>
      <h1>光伏实验室论文库</h1>
      <p>仅限实验室内部使用</p>
      <label>用户名<input v-model="loginUser" autocomplete="username" /></label>
      <label>密码<input v-model="loginPass" type="password" autocomplete="current-password" /></label>
      <button class="primary" type="submit">登录</button>
      <p v-if="loginError" class="hint login-error">{{ loginError }}</p>
    </form>
  </div>
  <div v-else class="shell">
    <header class="masthead">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">PV</span>
        <div>
          <h1>光伏实验室论文库</h1>
          <p class="brand-meta">
            <span>{{ stats.total }} 篇文献</span>
            <span>{{ stats.with_pdf }} 份 PDF</span>
            <span>{{ stats.oa }} 篇 OA</span>
          </p>
        </div>
      </div>
      <div class="who">
        <span class="who-name">{{ me.username }}</span>
        <span class="role-badge">{{ me.role }}</span>
        <button class="ghost" type="button" @click="doLogout">退出</button>
      </div>
    </header>
    <main class="workspace">
      <nav class="rail">
        <button data-nav="papers" :class="{ active: page === 'papers' }" type="button" @click="page = 'papers'">文献检索</button>
        <button data-nav="chat" :class="{ active: page === 'chat' }" type="button" @click="page = 'chat'">文献问答</button>
        <button data-nav="upload" :class="{ active: page === 'upload' }" type="button" @click="page = 'upload'">上传论文</button>
        <button data-nav="settings" :class="{ active: page === 'settings' }" type="button" @click="page = 'settings'">模型与图谱</button>
        <button
          v-if="me.role === 'admin'"
          data-nav="users"
          :class="{ active: page === 'users' }"
          type="button"
          @click="page = 'users'"
        >
          用户管理
        </button>
      </nav>
      <section v-if="page === 'papers'" class="stage papers-stage">
        <div class="page-heading">
          <h2>文献检索</h2>
          <p>按题名、作者、DOI、年份或关键词筛选馆藏。</p>
        </div>
        <div class="toolbar">
          <input v-model="keyword" type="search" placeholder="题名 / 作者" />
          <input v-model="doi" type="search" placeholder="DOI" />
          <input v-model="yearFrom" class="year" type="number" placeholder="起始年" />
          <input v-model="yearTo" class="year" type="number" placeholder="结束年" />
          <button class="chip" :class="{ active: oa === 'all' && pdf === 'all' && !topicId }" type="button" @click="oa = 'all'; pdf = 'all'; topicId = null">全部</button>
          <button class="chip" :class="{ active: oa === 'yes' }" type="button" @click="oa = 'yes'">OA</button>
          <button class="chip" :class="{ active: pdf === 'yes' }" type="button" @click="pdf = 'yes'">有 PDF</button>
        </div>
        <div class="kw-bar">
          <span class="muted">按关键词分类</span>
          <button
            v-for="item in topics"
            :key="item.id"
            class="chip"
            :class="{ active: topicId === item.id }"
            type="button"
            @click="setTopic(item.id)"
          >
            {{ item.name }} ({{ item.paper_count }})
          </button>
          <span v-if="!topics.length" class="hint">尚无关键词。上传或下载论文后会自动出现。</span>
        </div>
        <p v-if="error" class="hint">{{ error }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>年份</th>
                <th>题名</th>
                <th>作者</th>
                <th>关键词</th>
                <th>来源</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in papers" :key="item.id">
                <td>{{ item.year || item.published || '-' }}</td>
                <td class="title-cell">{{ item.title }}</td>
                <td>{{ item.authors }}</td>
                <td>
                  <span v-for="tag in item.keywords" :key="tag.id" class="tag" @click="setTopic(tag.id)">{{ tag.name }}</span>
                  <span v-if="!item.keywords?.length" class="muted">-</span>
                </td>
                <td>{{ item.source }}{{ item.uploaded_by ? ' / ' + item.uploaded_by : '' }}</td>
                <td class="ops">
                  <button v-if="item.has_pdf" class="primary" type="button" @click="openPreview(item.id)">预览</button>
                  <span v-else class="muted">无 PDF</span>
                  <button class="accent" type="button" @click="openGraph(item)">图谱</button>
                  <button class="ghost" type="button" @click="openEditKeywords(item)">改关键词</button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="loading" class="empty-note">正在检索...</p>
          <p v-else-if="!papers.length" class="empty-note">没有命中当前条件。可调整检索词，或改去上传论文。</p>
        </div>
      </section>
      <section v-else-if="page === 'chat'" class="stage chat-stage">
        <ChatPage @preview="openPreview" @graph="openGraph" />
      </section>
      <section v-else-if="page === 'upload'" class="stage form-stage">
        <form class="form" @submit.prevent="submitUpload">
          <h2>上传论文</h2>
          <p class="hint">默认用文件名作为题名。作者、DOI、年份、摘要、关键词均可选填；也可先点 AI 解析，从摘要抽取关键词。</p>
          <p class="hint">当前模型 {{ settings.ai.model || '未填写' }} / {{ settings.ai.ready ? '已配置密钥' : '尚未填写 API Key' }}</p>
          <label>PDF<input type="file" accept="application/pdf,.pdf" @change="onFile" /></label>
          <label>题名<input v-model="upload.title" placeholder="选择文件后自动填入文件名" /></label>
          <label>作者（选填）<input v-model="upload.authors" /></label>
          <label>DOI（选填）<input v-model="upload.doi" /></label>
          <label>年份（选填）<input v-model="upload.year" type="number" /></label>
          <label>摘要（选填）<textarea v-model="upload.description" rows="4" /></label>
          <label>关键词（选填，逗号分隔）<input v-model="upload.keywords" placeholder="TOPCon, perovskite" /></label>
          <div class="row">
            <button type="button" :disabled="parsing" @click="parseUpload">{{ parsing ? '解析中...' : 'AI 解析并填入' }}</button>
            <button class="primary" type="submit">保存入库</button>
          </div>
          <p v-if="uploadMsg" class="hint">{{ uploadMsg }}</p>
        </form>
      </section>
      <section v-else-if="page === 'settings'" class="stage form-stage">
        <div class="form wide">
          <h2>模型与图谱</h2>
          <p class="hint">地址、模型名和密钥先写在页面与 config.toml。图谱抽取提示词请在论文「图谱」弹窗中编辑；未自定义时，每类关键词共用同一条默认提示词。Neo4j 仅预留，审核通过后才会准备同步。</p>
          <h3>AI</h3>
          <label>API 地址<input v-model="settings.ai.base_url" :disabled="me.role !== 'admin'" placeholder="https://api.deepseek.com" /></label>
          <label>模型名称<input v-model="settings.ai.model" :disabled="me.role !== 'admin'" placeholder="deepseek-flash" /></label>
          <label>API Key<input v-model="settings.ai.api_key" :disabled="me.role !== 'admin'" type="password" placeholder="sk-..." /></label>
          <label>超时（秒）<input v-model.number="settings.ai.timeout_seconds" :disabled="me.role !== 'admin'" type="number" /></label>
          <button v-if="me.role === 'admin'" class="primary" type="button" @click="saveAi">保存 AI 配置</button>
          <h3>Neo4j（后期同步）</h3>
          <label class="check">
            <input v-model="settings.neo4j.enabled" :disabled="me.role !== 'admin'" type="checkbox" />
            启用同步（当前不会真正写入）
          </label>
          <label>URI<input v-model="settings.neo4j.uri" :disabled="me.role !== 'admin'" /></label>
          <label>用户<input v-model="settings.neo4j.user" :disabled="me.role !== 'admin'" /></label>
          <label>密码<input v-model="settings.neo4j.password" :disabled="me.role !== 'admin'" type="password" /></label>
          <label>数据库<input v-model="settings.neo4j.database" :disabled="me.role !== 'admin'" /></label>
          <button v-if="me.role === 'admin'" class="primary" type="button" @click="saveNeo4j">保存 Neo4j 配置</button>
          <h3>元数据与问答提示词</h3>
          <p class="hint">仅管理员可修改。图谱抽取提示词、各类关键词的提示词和 schema 已移到论文「图谱」弹窗。</p>
          <div v-for="item in settingsPrompts" :key="item.name" class="prompt-block">
            <label>{{ promptLabel(item.name) }}
              <textarea v-model="item.body" rows="6" :disabled="me.role !== 'admin'" />
            </label>
            <button v-if="me.role === 'admin'" class="primary" type="button" @click="savePrompt(item)">保存该提示词</button>
          </div>
          <h3>关键词</h3>
          <p class="hint">可在此改名称。抽取提示词与 schema 在论文图谱中编辑，默认共用同一条图谱提示词。</p>
          <div v-for="item in topics" :key="'kw-' + item.id" class="prompt-block">
            <label>{{ item.name }} ({{ item.paper_count }})
              <input v-model="item.name" />
            </label>
            <button class="primary" type="button" @click="saveKeywordPrompt(item)">保存名称</button>
          </div>
          <p v-if="!topics.length" class="hint">尚无关键词。上传或下载论文后会自动出现。</p>
          <p v-if="settingsMsg" class="hint">{{ settingsMsg }}</p>
        </div>
      </section>
      <section v-else class="stage form-stage">
        <form class="form inline" @submit.prevent="createUser">
          <h2>用户管理</h2>
          <div class="row">
            <input v-model="newUser.username" placeholder="username" />
            <input v-model="newUser.password" type="password" placeholder="password" />
            <select v-model="newUser.role">
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
            <button class="primary" type="submit">新增</button>
          </div>
          <p v-if="userMsg" class="hint">{{ userMsg }}</p>
        </form>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>用户</th>
                <th>角色</th>
                <th>状态</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in users" :key="user.id">
                <td>{{ user.username }}</td>
                <td><span class="role-badge">{{ user.role }}</span></td>
                <td>{{ user.active ? '启用' : '停用' }}</td>
                <td>
                  <button
                    type="button"
                    :class="user.active ? 'danger' : 'primary'"
                    :disabled="user.id === me.id"
                    @click="toggleUser(user)"
                  >
                    {{ user.active ? '停用' : '启用' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
    <div v-if="previewId" class="modal" @click.self="closePreview">
      <div class="modal-card">
        <div class="modal-bar">
          <span>PDF 预览</span>
          <button class="ghost" type="button" @click="closePreview">关闭</button>
        </div>
        <iframe :src="previewUrl" title="PDF 预览" />
      </div>
    </div>
    <div v-if="editKw.id" class="modal" @click.self="closeEditKeywords">
      <div class="modal-card small-modal">
        <div class="modal-bar">
          <span>修改关键词 / {{ editKw.title }}</span>
          <button class="ghost" type="button" @click="closeEditKeywords">关闭</button>
        </div>
        <form class="form" @submit.prevent="savePaperKeywords">
          <p class="hint">多个关键词用逗号分隔。相同名称会合并为同一个关键词。</p>
          <label>关键词<input v-model="editKw.text" /></label>
          <button class="primary" type="submit">保存关键词</button>
        </form>
      </div>
    </div>
    <div v-if="graphPaper" class="modal" @click.self="closeGraph">
      <div class="modal-card graph-modal">
        <div class="modal-bar">
          <span>知识图谱 / {{ graphPaper.title }}</span>
          <button class="ghost" type="button" @click="closeGraph">关闭</button>
        </div>
        <div class="graph-panel">
          <div class="graph-actions">
            <p class="hint">
              解析：<span class="status-pill">{{ parseStatusLabel(parseInfo.status) }}</span>
              <span v-if="parseInfo.page_count"> / {{ parseInfo.page_count }} 页 {{ parseInfo.chunk_count }} 块</span>
              <span class="sep">状态：</span>
              <span class="status-pill">{{ statusLabel(graphData.run?.status) }}</span>
              <span v-if="graphData.run?.model"> / 模型 {{ graphData.run.model }}</span>
              <span class="sep">中文图谱翻译已有节点和关系，不必重新抽取。</span>
            </p>
            <button
              v-if="parseInfo.has_pdf || graphPaper.has_pdf"
              type="button"
              :disabled="parsingPdf"
              @click="parsePaper(parseInfo.status === 'ok')"
            >
              {{ parsingPdf ? '解析中...' : (parseInfo.status === 'ok' ? '重新解析' : '解析正文') }}
            </button>
            <button class="primary" type="button" :disabled="extracting || parsingPdf || translating || !(parseInfo.has_pdf || graphPaper.has_pdf)" @click="extractGraph">
              {{ extracting ? '抽取中...' : 'AI 抽取图谱' }}
            </button>
            <button
              v-if="graphData.nodes.length"
              type="button"
              :disabled="translating || extracting"
              @click="translateGraph(false)"
            >
              {{ translating ? '翻译中...' : '翻译成中文' }}
            </button>
            <button
              v-if="graphData.run && graphData.run.status !== 'approved'"
              class="primary"
              type="button"
              @click="reviewGraph('approved')"
            >
              审核通过
            </button>
            <button
              v-if="graphData.run && graphData.run.status !== 'rejected'"
              class="danger"
              type="button"
              @click="reviewGraph('rejected')"
            >
              驳回
            </button>
            <input v-model="reviewNote" placeholder="审核意见（选填）" />
            <button
              v-if="graphData.nodes.length"
              class="chip"
              type="button"
              :class="{ active: graphLang === 'zh' }"
              @click="graphLang = 'zh'"
            >
              中文图谱
            </button>
            <button
              v-if="graphData.nodes.length"
              class="chip"
              type="button"
              :class="{ active: graphLang === 'en' }"
              @click="graphLang = 'en'"
            >
              原文图谱
            </button>
          </div>
          <p v-if="graphMsg" class="hint">{{ graphMsg }}</p>
          <div class="graph-work">
            <div class="graph-side">
              <h3>正文分块</h3>
              <p v-if="!(parseInfo.has_pdf || graphPaper.has_pdf)" class="hint">这篇没有 PDF，无法解析正文。</p>
              <p v-else-if="!parseChunks.length" class="hint">先解析 PDF 正文，再按块预览与抽取图谱。</p>
              <div v-else class="chunk-list">
                <details
                  v-for="chunk in parseChunks"
                  :key="chunk.chunk_index"
                  class="chunk-card"
                  :open="chunk.chunk_index === 0"
                >
                  <summary>
                    第 {{ chunk.chunk_index + 1 }} 块
                    <span v-if="chunk.section"> · {{ chunk.section }}</span>
                    <span v-if="chunk.page_from"> · p.{{ chunk.page_from }}–{{ chunk.page_to }}</span>
                    <span> · {{ chunk.char_count }} 字</span>
                  </summary>
                  <pre class="parse-preview">{{ chunk.preview }}</pre>
                </details>
              </div>
            </div>
            <div class="graph-side">
              <h3>图谱抽取提示词</h3>
              <p class="hint">所有关键词默认共用下面这条提示词。可按关键词改写，或另设 schema。</p>
              <label>默认提示词
                <textarea v-model="extractPromptBody" rows="7" :disabled="me.role !== 'admin'" />
              </label>
              <div class="row" v-if="me.role === 'admin'">
                <button class="primary" type="button" :disabled="promptSaving" @click="saveGraphExtractPrompt">保存默认提示词</button>
              </div>
              <div v-for="item in extractKeywords" :key="'gkw-' + item.id" class="prompt-block keyword-extract">
                <p class="kw-title">
                  {{ item.name }}
                  <span v-if="item.has_custom_prompt" class="status-pill">已改提示词</span>
                  <span v-else class="status-pill">共用默认</span>
                  <span v-if="item.has_custom_schema" class="status-pill">已设 schema</span>
                </p>
                <label>提示词
                  <textarea v-model="item.extract_prompt" rows="5" :disabled="me.role !== 'admin'" />
                </label>
                <label>Schema（选填）
                  <textarea
                    v-model="item.extract_schema"
                    rows="5"
                    :disabled="me.role !== 'admin'"
                    :placeholder="extractDefaultSchema || '可选：约束该类关键词抽出的节点/关系'"
                  />
                </label>
                <div class="row" v-if="me.role === 'admin'">
                  <button class="primary" type="button" :disabled="promptSaving" @click="saveGraphKeyword(item)">保存该类设置</button>
                  <button class="ghost" type="button" :disabled="promptSaving" @click="resetKeywordPrompt(item)">恢复默认提示词</button>
                </div>
              </div>
              <p v-if="!extractKeywords.length" class="hint">这篇还没有关键词。绑定关键词后可按类覆盖提示词或 schema。</p>
            </div>
          </div>
          <GraphChart v-if="chartNodes.length" :nodes="chartNodes" :edges="chartEdges" :zh="graphLang === 'zh'" />
          <p v-else class="hint">先解析 PDF 正文，再抽取图谱。抽取后将写入系统属性、正文中的材料/工艺/指标，并在此预览。</p>
        </div>
      </div>
    </div>
  </div>
</template>
