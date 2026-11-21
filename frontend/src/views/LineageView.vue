<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>数据血缘 · 前置关系与依赖复算</h2>
        <p class="page-desc">
          查看血缘节点的前置（上游）关系，调度依据这里的复算结果核对每张表的必需输入是否到齐。
        </p>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <div class="filter-bar">
      <label class="filter-item">
        <span>按表名查前置关系</span>
        <input v-model="tableName" data-testid="lineage-table-input" placeholder="如 dwd_channel_order_clean" />
      </label>
      <button class="btn primary" type="button" data-testid="lineage-query" @click="onLoadPrerequisites">查看前置关系</button>
    </div>

    <div v-if="prerequisitePayload" class="lineage-card" data-testid="prerequisite-card">
      <h3 class="section-title">
        血缘详情 · {{ prerequisitePayload.table }}
        <span v-if="prerequisitePayload.node_id" class="muted">（节点 {{ prerequisitePayload.node_id }}）</span>
      </h3>
      <p v-if="!prerequisitePayload.ok" class="warn-text">{{ prerequisitePayload.message }}</p>
      <table v-else class="data-table">
        <thead>
          <tr><th>上游节点ID</th><th>上游表</th><th>登记状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="pre in prerequisitePayload.prerequisites" :key="pre.node_id" :data-testid="`pre-${pre.node_id}`">
            <td>{{ pre.node_id }}</td>
            <td>{{ pre.table || '—' }}</td>
            <td>
              <span class="badge" :class="pre.registered ? 'badge-ready' : 'badge-blocked'">
                {{ pre.registered ? '已登记' : '未登记（缺失上游）' }}
              </span>
            </td>
          </tr>
          <tr v-if="!prerequisitePayload.prerequisites.length">
            <td colspan="3" class="empty-state">该节点为根节点，没有前置输入</td>
          </tr>
        </tbody>
      </table>
    </div>

    <h3 class="section-title">依赖复算（同一次复算覆盖门店、渠道两支链路）</h3>
    <div class="filter-bar">
      <label class="filter-item grow">
        <span>复算目标表（逗号分隔）</span>
        <input v-model="targetsText" data-testid="recompute-targets" />
      </label>
      <button class="btn primary" type="button" data-testid="recompute-run" @click="onRecompute">执行依赖复算</button>
    </div>

    <div v-if="recomputePayload" data-testid="recompute-result">
      <p class="page-desc">复算分区：<strong>{{ recomputePayload.partition }}</strong></p>
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">输入已齐</span>
          <strong class="stat-value ready">{{ recomputePayload.ready_tables.length }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">存在阻塞</span>
          <strong class="stat-value blocked">{{ recomputePayload.blocked_tables.length }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">缺失依赖条数</span>
          <strong class="stat-value blocked">{{ recomputePayload.missing_dependencies.length }}</strong>
        </article>
      </div>

      <table class="data-table">
        <thead>
          <tr><th>目标表</th><th>结论</th><th>已到齐输入（分区 / 出数时刻）</th><th>缺失输入（实际阻塞点）</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="table in Object.values(recomputePayload.tables)"
            :key="table.table"
            :data-testid="`recompute-row-${table.table}`"
            :class="table.ready ? 'row-ready' : 'row-blocked'"
          >
            <td>{{ table.table }}</td>
            <td>
              <span class="badge" :class="table.ready ? 'badge-ready' : 'badge-blocked'">
                {{ table.ready ? '可执行' : '阻塞' }}
              </span>
            </td>
            <td>
              <ul v-if="table.available_inputs.length" class="input-list">
                <li v-for="input in table.available_inputs" :key="input.table">
                  {{ input.table }} ｜ {{ input.partition }} ｜ {{ input.produced_at_text }}
                </li>
              </ul>
              <span v-else class="muted">无</span>
            </td>
            <td>
              <ul v-if="table.missing_inputs.length" class="blocker-list">
                <li v-for="(missing, i) in table.missing_inputs" :key="i">
                  <span class="blocker-kind">{{ missingKindLabel(missing.kind) }}</span>
                  {{ missing.table ? `上游表 ${missing.table}` : `未登记节点 ${missing.node_id}` }}
                </li>
              </ul>
              <span v-else class="ready-text">必需输入已齐</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  loadLineageRecompute,
  loadTablePrerequisites,
  type LineageRecompute,
} from '@/api/governance-service'

const DEFAULT_TARGETS = [
  'dwd_store_clean',
  'ads_store_daily_summary',
  'dwd_channel_order_clean',
  'ads_channel_daily_summary',
]

const tableName = ref('dwd_channel_order_clean')
const targetsText = ref(DEFAULT_TARGETS.join(','))
const prerequisitePayload = ref<Awaited<ReturnType<typeof loadTablePrerequisites>> | null>(null)
const recomputePayload = ref<LineageRecompute | null>(null)
const errorMessage = ref('')

const MISSING_LABELS: Record<string, string> = {
  unregistered_node: '缺失上游',
  partition_not_ready: '分区未就绪',
  unregistered_table: '表未登记',
}

function missingKindLabel(kind: string): string {
  return MISSING_LABELS[kind] ?? kind
}

async function onLoadPrerequisites() {
  errorMessage.value = ''
  if (!tableName.value.trim()) {
    errorMessage.value = '请输入要查询的表名'
    return
  }
  try {
    prerequisitePayload.value = await loadTablePrerequisites(tableName.value.trim())
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '前置关系查询失败'
  }
}

async function onRecompute() {
  errorMessage.value = ''
  const targets = targetsText.value.split(',').map((item) => item.trim()).filter(Boolean)
  if (!targets.length) {
    errorMessage.value = '请至少填写一个复算目标表'
    return
  }
  try {
    recomputePayload.value = await loadLineageRecompute(targets)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '依赖复算失败'
  }
}

onMounted(async () => {
  await onLoadPrerequisites()
  await onRecompute()
})
</script>
