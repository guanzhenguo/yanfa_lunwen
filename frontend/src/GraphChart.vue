<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  zh: { type: Boolean, default: true },
})

const el = ref(null)
let chart
let layoutCache = { key: '', pts: [] }

const colors = {
  Paper: '#f3c14e',
  Author: '#6ec8c2',
  Institution: '#7aa7e0',
  Keyword: '#d7a35a',
  Concept: '#9bb4c4',
  Material: '#8fd18a',
  Process: '#5ec2b7',
  Metric: '#e08b6a',
  File: '#8a969a',
  Year: '#a8b4b8',
}

const typeZh = {
  Paper: '论文',
  Author: '作者',
  Institution: '机构',
  Keyword: '关键词',
  Concept: '概念',
  Material: '材料',
  Process: '工艺',
  Metric: '指标',
  File: '文件',
  Year: '年份',
}

const TYPE_RING = {
  Paper: 0,
  Author: 1,
  Institution: 1,
  Keyword: 2,
  Material: 3,
  Process: 3,
  Metric: 4,
  Concept: 4,
  Year: 5,
  File: 5,
}

function typeName(type) {
  if (!props.zh) return type
  return typeZh[type] || type
}

function nodeId(node, index = 0) {
  return node.node_key || node.key || `n:${index}`
}

function graphKey(nodes, edges) {
  const n = nodes.map((node, i) => nodeId(node, i)).join('\0')
  const e = edges
    .map((edge) => `${edge.source_key || edge.source}\t${edge.target_key || edge.target}`)
    .join('\0')
  return `${n}||${e}`
}

function hashAngle(text) {
  let h = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 360) * (Math.PI / 180)
}

function layoutStatic(nodes, edges, width, height) {
  const n = nodes.length
  if (!n) return []
  const pts = nodes.map((node, i) => {
    const type = node.node_type || node.type || 'Concept'
    const ring = TYPE_RING[type] ?? 4
    const angle = hashAngle(nodeId(node, i))
    const radius = type === 'Paper' ? 0 : 90 + ring * 70
    return {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
      vx: 0,
      vy: 0,
      pin: type === 'Paper',
    }
  })
  const index = new Map(nodes.map((node, i) => [nodeId(node, i), i]))
  const pairs = []
  for (const edge of edges) {
    const a = index.get(edge.source_key || edge.source)
    const b = index.get(edge.target_key || edge.target)
    if (a == null || b == null || a === b) continue
    pairs.push([a, b])
  }
  const repulsion = 4200
  const spring = 0.035
  const rest = 150
  const ticks = Math.min(160, 40 + n)
  for (let iter = 0; iter < ticks; iter += 1) {
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        let dx = pts[j].x - pts[i].x
        let dy = pts[j].y - pts[i].y
        const d2 = dx * dx + dy * dy || 0.01
        const dist = Math.sqrt(d2)
        const force = repulsion / d2
        dx = (dx / dist) * force
        dy = (dy / dist) * force
        pts[i].vx -= dx
        pts[i].vy -= dy
        pts[j].vx += dx
        pts[j].vy += dy
      }
    }
    for (const [a, b] of pairs) {
      let dx = pts[b].x - pts[a].x
      let dy = pts[b].y - pts[a].y
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
      const force = (dist - rest) * spring
      dx = (dx / dist) * force
      dy = (dy / dist) * force
      pts[a].vx += dx
      pts[a].vy += dy
      pts[b].vx -= dx
      pts[b].vy -= dy
    }
    for (const pt of pts) {
      if (pt.pin) {
        pt.x = 0
        pt.y = 0
        pt.vx = 0
        pt.vy = 0
        continue
      }
      pt.x += pt.vx * 0.1
      pt.y += pt.vy * 0.1
      pt.vx *= 0.7
      pt.vy *= 0.7
    }
  }
  return fitToCanvas(pts, width, height)
}

function fitToCanvas(pts, width, height, pad = 56) {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const pt of pts) {
    minX = Math.min(minX, pt.x)
    minY = Math.min(minY, pt.y)
    maxX = Math.max(maxX, pt.x)
    maxY = Math.max(maxY, pt.y)
  }
  const boxW = maxX - minX || 1
  const boxH = maxY - minY || 1
  const scale = Math.min((width - pad * 2) / boxW, (height - pad * 2) / boxH)
  return pts.map((pt) => ({
    x: (pt.x - minX) * scale + pad,
    y: (pt.y - minY) * scale + pad,
  }))
}

function render() {
  if (!chart || !el.value) return
  const categories = [...new Set(props.nodes.map((node) => node.node_type || node.type).filter(Boolean))]
  const key = graphKey(props.nodes, props.edges)
  const width = el.value.clientWidth || 800
  const height = el.value.clientHeight || 520
  if (layoutCache.key !== key) {
    layoutCache = {
      key,
      pts: layoutStatic(props.nodes, props.edges, width, height),
    }
  }
  const pts = layoutCache.pts
  chart.setOption(
    {
      animation: false,
      backgroundColor: 'transparent',
      tooltip: {
        backgroundColor: '#171f23',
        borderColor: '#3a4c52',
        textStyle: { color: '#e8eef0' },
        formatter(item) {
          if (item.dataType === 'edge') return item.data.name || ''
          const properties = item.data.properties || {}
          const lines = Object.entries(properties)
            .slice(0, 8)
            .map(([k, value]) => `${k}: ${value ?? ''}`)
          return [`<b>${item.data.name || ''}</b>`, item.data.category, ...lines].filter(Boolean).join('<br/>')
        },
      },
      legend: {
        data: categories.map((name) => typeName(name)),
        bottom: 4,
        textStyle: { fontSize: 11, color: '#c5d4d8' },
      },
      series: [
        {
          type: 'graph',
          layout: 'none',
          roam: true,
          draggable: true,
          animation: false,
          categories: categories.map((name) => ({ name: typeName(name) })),
          data: props.nodes.map((node, i) => {
            const type = node.node_type || node.type || 'Concept'
            return {
              id: nodeId(node, i),
              name: node.label,
              category: typeName(type),
              x: pts[i]?.x ?? 0,
              y: pts[i]?.y ?? 0,
              symbolSize: type === 'Paper' ? 28 : 16,
              properties: node.properties || {},
              itemStyle: { color: colors[type] || '#f3c14e' },
            }
          }),
          links: props.edges.map((edge) => ({
            source: edge.source_key || edge.source,
            target: edge.target_key || edge.target,
            name: edge.rel_type || edge.type,
          })),
          label: { show: true, fontSize: 11, color: '#e8eef0' },
          edgeLabel: {
            show: true,
            fontSize: 9,
            color: '#8d9ea4',
            formatter: (item) => item.data.name || '',
          },
          lineStyle: { color: '#4a5c62', curveness: 0.12, width: 1.4 },
        },
      ],
    },
    true,
  )
}

function resize() {
  if (!chart || !el.value) return
  layoutCache = { key: '', pts: [] }
  chart.resize()
  render()
}

onMounted(() => {
  chart = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})

watch(() => [props.nodes, props.edges, props.zh], render, { deep: true })
</script>

<template>
  <div ref="el" class="graph-canvas" />
</template>

<style scoped>
.graph-canvas {
  width: 100%;
  height: 100%;
  min-height: 520px;
}
</style>
