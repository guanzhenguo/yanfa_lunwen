<script setup>
import { nextTick, onMounted, ref } from 'vue'

const emit = defineEmits(['preview', 'graph'])

const threads = ref([])
const threadId = ref(null)
const messages = ref([])
const draft = ref('')
const status = ref('就绪')
const running = ref(false)
const error = ref('')
const listEl = ref(null)

function api(path, options = {}) {
  return fetch(path, { credentials: 'include', ...options })
}

async function loadThreads() {
  const res = await api('/api/chat/threads')
  if (res.ok) threads.value = await res.json()
}

async function loadThread(id) {
  if (!id) {
    threadId.value = null
    messages.value = []
    status.value = '就绪'
    return
  }
  const res = await api(`/api/chat/threads/${id}`)
  if (!res.ok) {
    error.value = '无法打开对话'
    return
  }
  const body = await res.json()
  threadId.value = body.thread.id
  messages.value = body.messages || []
  status.value = '就绪'
  await scrollBottom()
}

async function newChat() {
  if (running.value) return
  const res = await api('/api/chat/threads', { method: 'POST' })
  if (!res.ok) return
  const thread = await res.json()
  threadId.value = thread.id
  messages.value = []
  error.value = ''
  status.value = '就绪'
  await loadThreads()
}

async function removeThread(id) {
  if (running.value) return
  await api(`/api/chat/threads/${id}`, { method: 'DELETE' })
  if (threadId.value === id) {
    threadId.value = null
    messages.value = []
  }
  await loadThreads()
}

function openSource(item) {
  if (!item?.paper_id) return
  emit('preview', item.paper_id)
}

function openGraph(item) {
  if (!item?.paper_id) return
  emit('graph', { id: item.paper_id, title: item.title })
}

async function scrollBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

async function readEvents(response, output) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.trim()) continue
      const event = JSON.parse(line)
      if (event.type === 'meta') {
        threadId.value = event.thread_id || threadId.value
        status.value = event.ai_ready ? '生成中' : '检索中'
      }
      if (event.type === 'sources') {
        output.sources = event.sources || []
        status.value = '生成中'
      }
      if (event.type === 'delta') {
        output.content += event.content || ''
        await scrollBottom()
      }
      if (event.type === 'error') {
        throw new Error(event.message || '问答失败')
      }
      if (event.type === 'done') {
        completed = event.status === 'completed'
        if (event.message) {
          output.content = event.message.content || output.content
          output.sources = event.message.sources || output.sources
          output.id = event.message.id
        }
      }
    }
    if (done) break
  }
  if (!completed) throw new Error('回答流在完成前中断，请重试')
}

async function submitMessage() {
  const message = draft.value.trim()
  if (!message || running.value) return
  draft.value = ''
  error.value = ''
  messages.value.push({ role: 'user', content: message, sources: [] })
  const output = { role: 'assistant', content: '', sources: [] }
  messages.value.push(output)
  running.value = true
  status.value = '检索中'
  await scrollBottom()
  try {
    const res = await api('/api/chat?stream=true', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, thread_id: threadId.value }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || body.error || `请求失败：${res.status}`)
    }
    await readEvents(res, output)
    await loadThreads()
    status.value = '就绪'
  } catch (err) {
    messages.value = messages.value.filter((item) => item !== output)
    error.value = err.message || String(err)
    status.value = '出错'
  } finally {
    running.value = false
    await scrollBottom()
  }
}

function onKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submitMessage()
  }
}

onMounted(async () => {
  await loadThreads()
})
</script>

<template>
  <div class="chat-layout">
    <aside class="chat-rail">
      <button class="primary" type="button" :disabled="running" @click="newChat">新对话</button>
      <div class="thread-list">
        <button
          v-for="item in threads"
          :key="item.id"
          class="thread"
          :class="{ active: threadId === item.id }"
          type="button"
          @click="loadThread(item.id)"
        >
          <span>{{ item.title }}</span>
          <em @click.stop="removeThread(item.id)">删除</em>
        </button>
        <p v-if="!threads.length" class="hint">还没有对话。直接提问会自动创建。</p>
      </div>
    </aside>
    <section class="chat-main">
      <div ref="listEl" class="chat-log" aria-live="polite">
        <div v-if="!messages.length" class="chat-empty">
          向文献库提问工艺、材料、电池结构或可靠性问题。<br />
          系统会先检索入库论文，再基于题名、摘要、关键词和图谱作答，并附来源。
        </div>
        <article v-for="(item, index) in messages" :key="item.id || index" class="bubble-row" :class="item.role">
          <div class="avatar" aria-hidden="true" />
          <div class="bubble">
            <pre class="content">{{ item.content || (item.role === 'assistant' && running ? '…' : '') }}</pre>
            <div v-if="item.sources?.length" class="sources">
              <button
                v-for="src in item.sources"
                :key="src.paper_id"
                class="source"
                type="button"
                @click="openSource(src)"
              >
                [{{ src.index }}] {{ src.title }}
                <span v-if="src.year"> · {{ src.year }}</span>
              </button>
              <button
                v-if="item.sources[0]"
                class="source ghost"
                type="button"
                @click="openGraph(item.sources[0])"
              >
                查看图谱
              </button>
            </div>
          </div>
        </article>
      </div>
      <form class="composer" @submit.prevent="submitMessage">
        <p v-if="error" class="hint">{{ error }}</p>
        <textarea
          v-model="draft"
          :disabled="running"
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          @keydown="onKey"
        />
        <div class="composer-row">
          <span class="hint">{{ status }}</span>
          <button class="primary" type="submit" :disabled="running || !draft.trim()">发送</button>
        </div>
      </form>
    </section>
  </div>
</template>
