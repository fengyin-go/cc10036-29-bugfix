<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>查询调度 · 依赖复算</h2>
        <p class="page-desc">
          按血缘前置关系核对必需输入，区分可执行计划与阻塞计划；循环依赖、缺失依赖一律拦截。
          当前复算分区：<strong>{{ recompute?.partition ?? '—' }}</strong>
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" data-testid="reload-recompute" @click="reload">重新复算</button>
        <button class="btn primary" type="button" data-testid="retry-failed" @click="onRetryFailed">失败重试</button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    <p v-if="actionMessage" class="action-text">{{ actionMessage }}</p>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">可执行计划</span>
        <strong class="stat-value ready">{{ recompute?.ready_count ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">阻塞计划</span>
        <strong class="stat-value blocked">{{ recompute?.blocked_count ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">循环依赖</span>
        <strong class="stat-value blocked">{{ recompute?.cycle_plans.length ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">未登记依赖</span>
        <strong class="stat-value blocked">{{ recompute?.unknown_dependencies.length ?? 0 }}</strong>
      </article>
    </div>

    <h3 class="section-title">拓扑执行次序（清洗先于汇总）</h3>
    <div class="topo-flow" data-testid="topology-flow">
      <template v-for="(item, idx) in topology?.ordered_plans ?? []" :key="item.plan">
        <span class="topo-node" :class="levelClass(item.level)" :data-status="item.status">
          L{{ item.level }} · {{ item.plan }}
          <small>（{{ item.status }}）</small>
        </span>
        <span v-if="idx < (topology?.ordered_plans.length ?? 0) - 1" class="topo-arrow">→</span>
      </template>
    </div>
    <p v-if="topology?.has_cycle" class="warn-text" data-testid="cycle-warning">
      检测到循环依赖，已排除出执行次序：{{ topology?.cycle_nodes.join('、') }}
    </p>

    <div class="plan-columns">
      <div class="plan-column">
        <h3 class="section-title ready-text">✅ 可执行计划（{{ recompute?.executable_plans.length ?? 0 }}）</h3>
        <table class="data-table">
          <thead>
            <tr><th>计划</th><th>层级</th><th>目标表</th><th>前置计划</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="plan in recompute?.executable_plans ?? []" :key="plan.plan_id" :data-testid="`ready-${plan.plan_id}`">
              <td>{{ plan.plan }}<small class="muted">（{{ plan.status }}）</small></td>
              <td>{{ plan.level ?? '—' }}</td>
              <td>{{ plan.target_table ?? '—' }}</td>
              <td>{{ plan.prerequisite_plans.join('、') || '无' }}</td>
              <td>
                <button class="link" type="button" @click="openDetail(plan.plan_id)">详情</button>
              </td>
            </tr>
            <tr v-if="!(recompute?.executable_plans.length)">
              <td colspan="5" class="empty-state">暂无满足全部依赖的计划</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="plan-column">
        <h3 class="section-title blocked-text">⛔ 阻塞计划（{{ recompute?.blocked_plans.length ?? 0 }}）</h3>
        <table class="data-table">
          <thead>
            <tr><th>计划</th><th>实际阻塞点</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="plan in recompute?.blocked_plans ?? []" :key="plan.plan_id" :data-testid="`blocked-${plan.plan_id}`">
              <td>{{ plan.plan }}<small class="muted">（{{ plan.status }}）</small></td>
              <td>
                <ul class="blocker-list">
                  <li v-for="(blocker, i) in plan.blockers" :key="i" :data-kind="blocker.kind">
                    <span class="blocker-kind">{{ blockerKindLabel(blocker.kind) }}</span>
                    {{ blocker.detail }}
                  </li>
                </ul>
              </td>
              <td><button class="link" type="button" @click="openDetail(plan.plan_id)">详情</button></td>
            </tr>
            <tr v-if="!(recompute?.blocked_plans.length)">
              <td colspan="3" class="empty-state">没有阻塞计划</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <h3 class="section-title">出数台账（真正产出的分区与出数时刻）</h3>
    <table class="data-table" data-testid="ledger-table">
      <thead>
        <tr><th>表</th><th>分区</th><th>出数时刻</th><th>来源计划</th></tr>
      </thead>
      <tbody>
        <tr v-for="output in ledger?.outputs ?? []" :key="`${output.table}-${output.partition}`">
          <td>{{ output.table }}</td>
          <td>{{ output.partition }}</td>
          <td>{{ output.produced_at_text }}</td>
          <td>{{ output.source_plan || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <div v-if="detail" class="modal-backdrop" data-testid="plan-detail-modal" @click.self="detail = null">
      <div class="modal">
        <h3>调度详情 · {{ detail.plan['计划名称'] }}</h3>
        <p>
          <span class="badge" :class="detail.dependency_ready ? 'badge-ready' : 'badge-blocked'">
            {{ detail.state }}
          </span>
          <span class="muted">
            拓扑层级：{{ detail.level ?? '—' }} ｜ 执行周期：{{ detail.plan['执行周期'] }}
          </span>
        </p>
        <dl class="detail-list">
          <dt>查询语句</dt>
          <dd><code>{{ detail.plan['查询语句'] }}</code></dd>
          <dt>目标表</dt>
          <dd>{{ detail.target_table ?? '无（不涉及血缘表产出）' }}</dd>
          <dt>前置计划</dt>
          <dd>{{ detail.prerequisite_plans.join('、') || '无依赖，可按原方式直接开跑' }}</dd>
          <dt>阻塞点</dt>
          <dd>
            <ul v-if="detail.blockers.length" class="blocker-list">
              <li v-for="(blocker, i) in detail.blockers" :key="i">{{ blocker.detail }}</li>
            </ul>
            <span v-else class="ready-text">无阻塞，必需输入已齐</span>
          </dd>
          <dt>最新产出</dt>
          <dd v-if="detail.latest_output">
            {{ detail.latest_output.partition }} ｜ {{ detail.latest_output.produced_at_text }}
          </dd>
          <dd v-else class="muted">尚未产出</dd>
        </dl>
        <div class="page-actions">
          <button class="btn" type="button" @click="detail = null">关闭</button>
          <button
            v-if="['待调度', '调度失败'].includes(detail.plan.status)"
            class="btn primary"
            type="button"
            data-testid="detail-start"
            @click="onStart(detail.plan.id)"
          >
            开始执行
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { runAction } from '@/api/backend-service'
import {
  loadLedger,
  loadPlanDetail,
  loadSchedulerRecompute,
  loadTopology,
  retryFailed,
  type LedgerOutput,
  type PlanDetail,
  type SchedulerRecompute,
} from '@/api/governance-service'

const recompute = ref<SchedulerRecompute | null>(null)
const topology = ref<Awaited<ReturnType<typeof loadTopology>> | null>(null)
const ledger = ref<{ outputs: LedgerOutput[] } | null>(null)
const detail = ref<PlanDetail | null>(null)
const errorMessage = ref('')
const actionMessage = ref('')

const KIND_LABELS: Record<string, string> = {
  unregistered_node: '缺失上游',
  unregistered_dependency: '未登记依赖',
  unregistered_table: '表未登记',
  dependency_not_completed: '前置未完成',
  partition_not_ready: '输入分区未就绪',
  cyclic_dependency: '循环依赖',
}

function blockerKindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind
}

function levelClass(level: number): string {
  return `topo-level-${level % 4}`
}

async function reload() {
  errorMessage.value = ''
  try {
    const [recomputePayload, topologyPayload, ledgerPayload] = await Promise.all([
      loadSchedulerRecompute(),
      loadTopology(),
      loadLedger(),
    ])
    recompute.value = recomputePayload
    topology.value = topologyPayload
    ledger.value = ledgerPayload
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '依赖复算加载失败'
  }
}

async function openDetail(planId: number) {
  actionMessage.value = ''
  try {
    detail.value = await loadPlanDetail(planId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度详情加载失败'
  }
}

async function onStart(planId: number) {
  actionMessage.value = ''
  errorMessage.value = ''
  const result = await runAction('query_scheduler', planId, '开始执行')
  if (!result.ok) {
    errorMessage.value = result.message
    return
  }
  actionMessage.value = `计划已进入执行中：${result.entry?.['计划名称'] ?? planId}`
  await reload()
  detail.value = await loadPlanDetail(planId)
}

async function onRetryFailed() {
  actionMessage.value = ''
  errorMessage.value = ''
  try {
    const result = await retryFailed()
    actionMessage.value = result.retried_count
      ? `已重试 ${result.retried_count} 个失败计划`
      : '没有可重试的失败计划（依赖未满足的已被拦截）'
    if (result.blocked.length) {
      actionMessage.value += `；拦截：${result.blocked.map((b) => b.plan).join('、')}`
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '失败重试调用失败'
  }
}

onMounted(reload)
</script>
