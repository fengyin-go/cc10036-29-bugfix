"""查询调度领域服务：任务编排、依赖复算、拓扑排序与依赖守卫。

修复要点：
- 依赖图边方向修正：前置任务 -> 当前计划，拓扑排序保证清洗先于汇总；
- 未登记的依赖（血缘节点或调度计划缺失）不再抛错，而是作为阻塞原因返回；
- 依赖复算同时核对「前置计划完成情况」和「血缘表必需输入（分区）是否到齐」，
  明确区分可执行计划与阻塞计划，并标出实际阻塞点；
- 循环依赖、缺失依赖一律拦截，开始执行与失败重试走同一道守卫；
- 无依赖的旧计划保持原行为，可直接开跑；
- 完成调度时把产出分区与出数时刻回写血缘登记表，形成出数台账。
"""
from __future__ import annotations

import re
from typing import Any

from app.lineage_registry import DEFAULT_PARTITION, lineage_registry
from app.services.base import BaseModuleService
from app.services.data_lineage import DataLineageService
from app.store import store

_PRIORITY_RANK = {"高": 0, "中": 1, "低": 2}
_EXECUTABLE_STATUS = {"待调度", "调度失败"}
_TARGET_TABLE_PATTERN = re.compile(
    r"(?:INSERT\s+INTO|REFRESH\s+MATERIALIZED\s+VIEW)\s+([a-zA-Z_][\w.]*)",
    re.IGNORECASE,
)


class QuerySchedulerService(BaseModuleService):
    MODULE = "query_scheduler"
    ENTITY = "调度计划"
    OPERATION_TERM = "查询"
    LIST_FIELDS = ["计划名称", "查询语句", "执行周期", "依赖任务", "超时分钟", "失败重试", "优先级"]
    REQUIRED_FIELDS = ["计划名称", "查询语句", "执行周期"]
    STATUS_ORDER = ["待调度", "执行中", "已完成", "调度失败", "已暂停"]
    ACTION_RULES = {"开始执行": "执行中", "完成调度": "已完成", "标记失败": "调度失败", "暂停计划": "已暂停"}
    NEGATIVE_ACTIONS = ["标记失败"]

    def __init__(self) -> None:
        # 执行事件流水（与血缘登记表的分区台账互补）。
        self._run_events: list[dict[str, Any]] = []

    # ---- 依赖图与拓扑 ----

    @staticmethod
    def _parse_deps(raw: Any) -> list[str]:
        return [part.strip() for part in str(raw or "").split(",") if part.strip()]

    def _plan_index(self) -> dict[str, dict[str, Any]]:
        return {str(row.get("计划名称", "")): row for row in store.rows(self.MODULE)}

    def build_dependency_graph(self) -> dict[str, Any]:
        """构建依赖图：plan_name -> 前置计划名列表（前置 -> 当前的边在拓扑里展开）。"""
        rows = store.rows(self.MODULE)
        graph: dict[str, list[str]] = {}
        unknown: list[dict[str, str]] = []
        known = {str(row.get("计划名称", "")) for row in rows}
        for row in rows:
            name = str(row.get("计划名称", ""))
            deps = self._parse_deps(row.get("依赖任务"))
            graph[name] = deps
            for dep in deps:
                if dep not in known:
                    unknown.append({"plan": name, "dependency": dep})
        return {
            "ok": True,
            "nodes": len(rows),
            "graph": graph,
            "unknown_dependencies": unknown,
        }

    def topological_order(self) -> dict[str, Any]:
        """按依赖拓扑排序：前置先于后继（清洗在前、汇总在后），同层按优先级与登记次序。"""
        graph_info = self.build_dependency_graph()
        graph: dict[str, list[str]] = graph_info["graph"]
        rows = store.rows(self.MODULE)
        sequence = {str(row.get("计划名称", "")): idx for idx, row in enumerate(rows)}

        # 入度 = 已知前置任务的条数；未知前置不参与图遍历，但会在复算里阻塞计划。
        in_degree = {name: 0 for name in graph}
        dependents: dict[str, list[str]] = {name: [] for name in graph}
        for name, deps in graph.items():
            for dep in deps:
                if dep in graph:
                    in_degree[name] += 1
                    dependents[dep].append(name)

        def sort_key(name: str) -> tuple[int, int, int, str]:
            row = store.rows(self.MODULE)[sequence[name]]
            return (
                level.get(name, 0),
                _PRIORITY_RANK.get(str(row.get("优先级", "")), 3),
                sequence[name],
                name,
            )

        level = {name: 0 for name, deg in in_degree.items() if deg == 0}
        ready = [name for name, deg in in_degree.items() if deg == 0]
        order: list[str] = []
        levels: list[dict[str, Any]] = []
        while ready:
            ready.sort(key=sort_key)
            node = ready.pop(0)
            order.append(node)
            levels.append({
                "plan": node,
                "level": level[node],
                "status": str(store.rows(self.MODULE)[sequence[node]].get("status", "")),
            })
            for successor in dependents[node]:
                in_degree[successor] -= 1
                level[successor] = max(level.get(successor, 0), level[node] + 1)
                if in_degree[successor] == 0:
                    ready.append(successor)

        cycle_nodes = sorted(name for name, deg in in_degree.items() if deg > 0)
        return {
            "ok": True,
            "plan_count": len(graph),
            "execution_order": order,
            "ordered_plans": levels,
            "has_cycle": bool(cycle_nodes),
            "cycle_nodes": cycle_nodes,
            "unknown_dependencies": graph_info["unknown_dependencies"],
        }

    # ---- 依赖复算（血缘前置关系 -> 调度可执行性） ----

    @staticmethod
    def target_table_of(row: dict[str, Any]) -> str | None:
        match = _TARGET_TABLE_PATTERN.search(str(row.get("查询语句", "")))
        return match.group(1) if match else None

    def _lineage_service(self) -> DataLineageService:
        svc = next(
            (s for s in self._all_services() if isinstance(s, DataLineageService)),
            None,
        )
        if svc is None:
            svc = DataLineageService()
        return svc

    @staticmethod
    def _all_services() -> list[BaseModuleService]:
        from app.services import SERVICES

        return list(SERVICES.values())

    def _task_blockers(self, row: dict[str, Any], plan_index: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
        """核对计划级前置：未登记的计划依赖、未完成的前置计划都构成阻塞。"""
        blockers: list[dict[str, str]] = []
        for dep in self._parse_deps(row.get("依赖任务")):
            dep_row = plan_index.get(dep)
            if dep_row is None:
                blockers.append({
                    "kind": "unregistered_dependency",
                    "dependency": dep,
                    "detail": f"前置计划「{dep}」未登记，无法确认产出",
                })
            elif dep_row.get("status") != "已完成":
                blockers.append({
                    "kind": "dependency_not_completed",
                    "dependency": dep,
                    "detail": f"前置计划「{dep}」当前状态为{dep_row.get('status')}，尚未完成",
                })
        return blockers

    def recompute_plan_dependencies(self, partition: str = DEFAULT_PARTITION) -> dict[str, Any]:
        """依赖复算主入口：输出可区分可执行/阻塞计划的复算数据。"""
        rows = store.rows(self.MODULE)
        plan_index = self._plan_index()
        topology = self.topological_order()
        cycle_nodes = set(topology["cycle_nodes"])
        level_map = {item["plan"]: item["level"] for item in topology["ordered_plans"]}

        # 一次复算覆盖全部待调度/失败计划涉及的血缘表（可包含多支链路）。
        targets: list[str] = []
        target_of_plan: dict[str, str | None] = {}
        for row in rows:
            table = self.target_table_of(row)
            target_of_plan[str(row.get("计划名称", ""))] = table
            if table and table not in targets:
                targets.append(table)

        lineage_payload = self._lineage_service().recompute_dependency_inputs(targets, partition)
        table_results: dict[str, dict[str, Any]] = lineage_payload["tables"]

        executable_plans: list[dict[str, Any]] = []
        blocked_plans: list[dict[str, Any]] = []
        for row in rows:
            if row.get("status") not in _EXECUTABLE_STATUS:
                continue
            name = str(row.get("计划名称", ""))
            table = target_of_plan[name]
            blockers = self._task_blockers(row, plan_index)
            if name in cycle_nodes:
                blockers.append({
                    "kind": "cyclic_dependency",
                    "dependency": name,
                    "detail": f"计划「{name}」处于循环依赖中，禁止执行",
                })
            table_block: dict[str, Any] | None = None
            if table is not None:
                table_block = table_results.get(table)
                if table_block is None or not table_block.get("registered", False):
                    blockers.append({
                        "kind": "unregistered_table",
                        "dependency": table or "",
                        "detail": f"目标表「{table}」未在血缘登记，无法核对输入",
                    })
                elif not table_block.get("ready", False):
                    for missing in table_block.get("missing_inputs", []):
                        blockers.append({
                            "kind": missing.get("kind", "missing_input"),
                            "dependency": missing.get("table") or f"血缘节点{missing.get('node_id')}",
                            "detail": self._describe_missing_input(table, missing),
                        })

            entry = {
                "plan_id": row.get("id"),
                "plan": name,
                "status": row.get("status"),
                "level": level_map.get(name),
                "target_table": table,
                "prerequisite_plans": self._parse_deps(row.get("依赖任务")),
                "lineage_check": table_block,
            }
            if blockers:
                blocked_plans.append({**entry, "blockers": blockers})
            else:
                executable_plans.append({**entry, "blockers": []})

        return {
            "ok": True,
            "partition": partition,
            "executable_plans": executable_plans,
            "blocked_plans": blocked_plans,
            "ready_count": len(executable_plans),
            "blocked_count": len(blocked_plans),
            "cycle_plans": topology["cycle_nodes"],
            "unknown_dependencies": topology["unknown_dependencies"],
            "lineage_recompute": lineage_payload,
        }

    @staticmethod
    def _describe_missing_input(target_table: str, missing: dict[str, str]) -> str:
        if missing.get("kind") == "unregistered_node":
            return (
                f"表「{target_table}」的前置血缘节点 {missing.get('node_id')} 未登记，"
                "存在缺失上游"
            )
        return (
            f"表「{target_table}」缺少上游「{missing.get('table')}」的必需分区输入"
        )

    def get_ready_plans(self) -> list[dict[str, Any]]:
        """可执行计划：无任何任务/血缘/循环阻塞，待执行里不再残留错误的就绪计划。"""
        recompute = self.recompute_plan_dependencies()
        ready_ids = {item["plan_id"] for item in recompute["executable_plans"]}
        return [
            row for row in store.rows(self.MODULE)
            if row.get("id") in ready_ids
        ]

    def get_blocked_plans(self) -> list[dict[str, Any]]:
        """阻塞计划及实际阻塞点。"""
        return self.recompute_plan_dependencies()["blocked_plans"]

    def plan_detail(self, entry_id: int) -> dict[str, Any] | None:
        """调度详情：拓扑层级、前置、阻塞点与目标表最新产出一并标出。"""
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return None
        recompute = self.recompute_plan_dependencies()
        name = str(row.get("计划名称", ""))
        table = self.target_table_of(row)
        matched = next(
            (item for item in [*recompute["executable_plans"], *recompute["blocked_plans"]]
             if item["plan_id"] == entry_id),
            None,
        )
        latest_output = lineage_registry.get(table) if table else None
        can_start = row.get("status") in _EXECUTABLE_STATUS
        dependency_ready = matched is not None and not matched.get("blockers")
        if not can_start:
            state = str(row.get("status", ""))
        else:
            state = "可执行" if dependency_ready else "阻塞"
        return {
            "ok": True,
            "plan": row,
            "state": state,
            "level": matched.get("level") if matched else None,
            "target_table": table,
            "prerequisite_plans": self._parse_deps(row.get("依赖任务")),
            "executable": can_start and dependency_ready,
            "dependency_ready": dependency_ready,
            "blockers": matched.get("blockers", []) if matched else [],
            "lineage_check": matched.get("lineage_check") if matched else None,
            "latest_output": latest_output.to_dict() if latest_output else None,
        }

    # ---- 执行守卫与重试 ----

    def _guard_start(self, row: dict[str, Any]) -> str | None:
        """开始执行前的统一依赖守卫，重试也走这里，不能绕过实际依赖。"""
        recompute = self.recompute_plan_dependencies()
        name = str(row.get("计划名称", ""))
        blocked = next(
            (item for item in recompute["blocked_plans"] if item["plan_id"] == row.get("id")),
            None,
        )
        if blocked is not None:
            reasons = "；".join(b["detail"] for b in blocked["blockers"])
            return f"计划「{name}」依赖未满足，已拦截：{reasons}"
        if name in recompute["cycle_plans"]:
            return f"计划「{name}」存在循环依赖，禁止执行"
        return None

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        if action not in self.ACTION_RULES:
            return None, f"动作「{action}」不属于{self.MODULE}可执行范围"

        if action == "开始执行":
            if entry.get("status") not in _EXECUTABLE_STATUS:
                return None, (
                    f"计划「{entry.get('计划名称')}」当前状态为{entry.get('status')}，"
                    "仅待调度/调度失败的计划可以开始执行"
                )
            guard_message = self._guard_start(entry)
            if guard_message:
                return None, guard_message

        result_entry, message = super().run_action(entry_id, action)

        if action == "开始执行" and result_entry is not None:
            self._run_events.append({
                "plan": entry.get("计划名称"),
                "event": "开始执行",
                "at": lineage_registry.clock(),
                "status": result_entry.get("status"),
            })

        if action == "完成调度" and result_entry is not None:
            table = self.target_table_of(entry)
            if table:
                output = lineage_registry.register_output(
                    table, DEFAULT_PARTITION, source_plan=str(entry.get("计划名称", ""))
                )
                self._run_events.append({
                    "plan": entry.get("计划名称"),
                    "event": "完成调度",
                    "at": output.produced_at,
                    "table": table,
                    "partition": DEFAULT_PARTITION,
                })
        return result_entry, message

    def retry_failed(self) -> dict[str, Any]:
        """重试失败计划：复用同一道依赖守卫，依赖未满足时不会被重试绕过。"""
        rows = store.rows(self.MODULE)
        retried = 0
        blocked: list[dict[str, str]] = []
        for row in rows:
            if row.get("status") != "调度失败":
                continue
            max_retries = _parse_int(row.get("失败重试"), 3)
            retry_count = int(row.get("_retry_count", 0))
            if retry_count >= max_retries:
                blocked.append({"plan": str(row.get("计划名称", "")), "reason": "重试次数已用尽"})
                continue
            guard_message = self._guard_start(row)
            if guard_message:
                blocked.append({"plan": str(row.get("计划名称", "")), "reason": guard_message})
                continue
            row["_retry_count"] = retry_count + 1
            _, message = self.run_action(int(row["id"]), "开始执行")
            retried += 1
        return {"ok": True, "retried_count": retried, "blocked": blocked}

    def execution_ledger(self) -> dict[str, Any]:
        """出数台账：真正产出的分区、出数时刻与来源计划。"""
        return {
            "ok": True,
            "partition": DEFAULT_PARTITION,
            "outputs": lineage_registry.ledger(),
            "run_events": self._run_events,
        }

    # ---- 列表按拓扑次序返回（修复日汇总排到清洗前的错位） ----

    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows, total = super().list_entries(
            filters=filters, keyword=keyword, status=status, page=1, size=1_000_000
        )
        topology = self.topological_order()
        order_index = {name: idx for idx, name in enumerate(topology["execution_order"])}
        cycle_names = set(topology["cycle_nodes"])
        # 无环计划按拓扑层级排序；陷入循环的计划沉底，避免它们冒充可执行顺序。
        rows.sort(key=lambda r: (
            str(r.get("计划名称", "")) not in order_index,
            order_index.get(str(r.get("计划名称", "")), len(order_index)),
            int(r.get("id", 0)),
        ))
        start = (page - 1) * size
        return rows[start:start + size], total

    def domain_snapshot(self) -> dict[str, Any]:
        base = super().domain_snapshot()
        base["artifact"] = "查询调度数据集"
        recompute = self.recompute_plan_dependencies()
        base["ready_count"] = recompute["ready_count"]
        base["blocked_count"] = recompute["blocked_count"]
        return base


def _parse_int(val: Any, default: int) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default
