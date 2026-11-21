/** 数据治理（查询调度 + 数据血缘）专用接口封装。 */
import { fetchJson } from './client'

export type Blocker = {
  kind: string
  dependency: string
  detail: string
}

export type RecomputedPlan = {
  plan_id: number
  plan: string
  status: string
  level: number | null
  target_table: string | null
  prerequisite_plans: string[]
  lineage_check: Record<string, unknown> | null
  blockers: Blocker[]
}

export type SchedulerRecompute = {
  ok: boolean
  partition: string
  executable_plans: RecomputedPlan[]
  blocked_plans: RecomputedPlan[]
  ready_count: number
  blocked_count: number
  cycle_plans: string[]
  unknown_dependencies: { plan: string; dependency: string }[]
  lineage_recompute: {
    ready_tables: string[]
    blocked_tables: string[]
    missing_dependencies: Record<string, string>[]
    tables: Record<string, unknown>
  }
}

export type PlanDetail = {
  ok: boolean
  plan: {
    id: number
    计划名称: string
    查询语句: string
    执行周期: string
    依赖任务: string
    优先级: string
    status: string
  }
  state: string
  level: number | null
  target_table: string | null
  prerequisite_plans: string[]
  executable: boolean
  dependency_ready: boolean
  blockers: Blocker[]
  lineage_check: Record<string, unknown> | null
  latest_output: {
    table: string
    partition: string
    produced_at_text: string
    source_plan: string
  } | null
}

export type LedgerOutput = {
  table: string
  partition: string
  produced_at: number
  produced_at_text: string
  source_plan: string
}

export type Prerequisite = {
  node_id: string
  table: string
  registered: boolean
}

export type LineageRecompute = {
  ok: boolean
  partition: string
  target_count: number
  ready_tables: string[]
  blocked_tables: string[]
  missing_dependencies: Record<string, string>[]
  tables: Record<
    string,
    {
      table: string
      registered: boolean
      ready: boolean
      available_inputs: LedgerOutput[]
      missing_inputs: { node_id: string; table: string; kind: string }[]
      blockers: Record<string, string>[]
    }
  >
}

export async function loadSchedulerRecompute(): Promise<SchedulerRecompute> {
  return fetchJson<SchedulerRecompute>('/api/analytics/scheduler/recompute')
}

export async function loadTopology(): Promise<{
  execution_order: string[]
  ordered_plans: { plan: string; level: number; status: string }[]
  has_cycle: boolean
  cycle_nodes: string[]
  unknown_dependencies: { plan: string; dependency: string }[]
}> {
  return fetchJson('/api/analytics/scheduler/topology')
}

export async function loadPlanDetail(planId: number): Promise<PlanDetail> {
  return fetchJson<PlanDetail>(`/api/analytics/scheduler/plans/${planId}/detail`)
}

export async function loadLedger(): Promise<{ ok: boolean; partition: string; outputs: LedgerOutput[] }> {
  return fetchJson('/api/analytics/scheduler/ledger')
}

export async function loadBlockedPlans(): Promise<{ ok: boolean; items: RecomputedPlan[] }> {
  return fetchJson('/api/analytics/scheduler/blocked')
}

export async function retryFailed(): Promise<{
  ok: boolean
  retried_count: number
  blocked: { plan: string; reason: string }[]
}> {
  return fetchJson('/api/analytics/scheduler/retry-failed', { method: 'POST' })
}

export async function loadTablePrerequisites(tableName: string): Promise<{
  ok: boolean
  table: string
  node_id?: string
  prerequisite_count?: number
  prerequisites: Prerequisite[]
  message?: string
}> {
  return fetchJson(`/api/analytics/lineage/table/${encodeURIComponent(tableName)}/prerequisites`)
}

export async function loadLineageRecompute(targets: string[]): Promise<LineageRecompute> {
  const query = targets.map((t) => `targets=${encodeURIComponent(t)}`).join('&')
  return fetchJson<LineageRecompute>(`/api/analytics/lineage/recompute?${query}`)
}
