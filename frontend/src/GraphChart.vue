<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
})

const el = ref(null)
let chart

const colors = {
  Paper: '#154f5b',
  Author: '#8a5a2b',
  Institution: '#5b3d6b',
  Keyword: '#3d6b4f',
  Concept: '#2f5d8a',
  Material: '#7a4a1f',
  Process: '#1f6b6b',
  Metric: '#6b3d3d',
  File: '#5d574e',
  Year: '#6e6558',
}

function render() {
  if (!chart) return
  const categories = [...new Set(props.nodes.map((node) => node.node_type || node.type).filter(Boolean))]
  chart.setOption(
    {
      tooltip: {
        formatter(item) {
          if (item.dataType === 'edge') return item.data.name || ''
          const properties = item.data.properties || {}
          const lines = Object.entries(properties)
            .slice(0, 8)
            .map(([key, value]) => `${key}: ${value ?? ''}`)
          return [`<b>${item.data.name || ''}</b>`, item.data.category, ...lines].filter(Boolean).join('<br/>')
        },
      },
      legend: { data: categories, bottom: 4, textStyle: { fontSize: 11 } },
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          categories: categories.map((name) => ({ name })),
          data: props.nodes.map((node) => {
            const type = node.node_type || node.type || 'Concept'
            return {
              id: node.node_key || node.key,
              name: node.label,
              category: type,
              properties: node.properties || {},
              itemStyle: { color: colors[type] || '#154f5b' },
            }
          }),
          links: props.edges.map((edge) => ({
            source: edge.source_key || edge.source,
            target: edge.target_key || edge.target,
            name: edge.rel_type || edge.type,
          })),
          label: { show: true, fontSize: 11 },
          edgeLabel: {
            show: true,
            fontSize: 9,
            color: '#6e6558',
            formatter: (item) => item.data.name || '',
          },
          force: { repulsion: 340, edgeLength: [70, 150] },
          lineStyle: { color: '#b7aea0', curveness: 0.12, width: 1.4 },
        },
      ],
    },
    true,
  )
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})

watch(() => [props.nodes, props.edges], render, { deep: true })
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
