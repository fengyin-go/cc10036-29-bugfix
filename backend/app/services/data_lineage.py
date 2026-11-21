"""数据血缘领域服务：图结构计算、影响分析、上下游追踪、依赖复算。"""
from __future__ import annotations

from typing import Any

from app.lineage_registry import DEFAULT_PARTITION, lineage_registry
from app.services.base import BaseModuleService
from app.store import store
from app.analytics_engine import LineageGraph, LineageNode


class DataLineageService(BaseModuleService):
    MODULE = "data_lineage"
    ENTITY = "血缘节点"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["节点名称", "节点类型", "上游列表", "下游列表", "数据量级", "更新频率", "负责人"]
    REQUIRED_FIELDS = ["节点名称", "节点类型", "上游列表"]
    STATUS_ORDER = ["在线", "已下线", "已停用"]
    ACTION_RULES = {"标记下线": "已下线", "停用节点": "已停用"}
    NEGATIVE_ACTIONS = ["停用节点"]

    # ---- 业务方法 ----

    def build_graph_from_store(self) -> LineageGraph:
        """从Store中构建血缘图。"""
        graph = LineageGraph()
        rows = store.rows(self.MODULE)
        for row in rows:
            if row.get("status") != "在线":
                continue
            node_id = str(row.get("id", ""))
            upstream_raw = str(row.get("上游列表", ""))
            downstream_raw = str(row.get("下游列表", ""))
            node = LineageNode(
                node_id=node_id,
                node_name=str(row.get("节点名称", "")),
                node_type=str(row.get("节点类型", "")),
                upstream_ids=[u.strip() for u in upstream_raw.split(",") if u.strip()],
                downstream_ids=[d.strip() for d in downstream_raw.split(",") if d.strip()],
            )
            graph.add_node(node)
        return graph

    def compute_upstream(self, node_id: str) -> dict[str, Any]:
        """计算上游血缘链。"""
        graph = self.build_graph_from_store()
        entry = store.find(self.MODULE, int(node_id))
        if entry is None:
            return {"ok": False, "message": f"节点 {node_id} 不存在"}
        chains = graph.upstream_chain(node_id)
        return {
            "ok": True,
            "node_name": str(entry.get("节点名称", "")),
            "node_type": str(entry.get("节点类型", "")),
            "upstream_chains": chains,
            "chain_count": len(chains),
            "max_depth": max((len(c) for c in chains), default=0),
        }

    def compute_downstream(self, node_id: str) -> dict[str, Any]:
        """计算下游影响链。"""
        graph = self.build_graph_from_store()
        entry = store.find(self.MODULE, int(node_id))
        if entry is None:
            return {"ok": False, "message": f"节点 {node_id} 不存在"}
        chains = graph.downstream_chain(node_id)
        return {
            "ok": True,
            "node_name": str(entry.get("节点名称", "")),
            "node_type": str(entry.get("节点类型", "")),
            "downstream_chains": chains,
            "chain_count": len(chains),
            "max_depth": max((len(c) for c in chains), default=0),
        }

    def impact_analysis(self, node_id: str) -> dict[str, Any]:
        """变更影响分析：找出所有下游节点。"""
        graph = self.build_graph_from_store()
        entry = store.find(self.MODULE, int(node_id))
        if entry is None:
            return {"ok": False, "message": f"节点 {node_id} 不存在"}
        impacted = graph.impact_analysis(node_id)
        return {
            "ok": True,
            "node_name": str(entry.get("节点名称", "")),
            "impacted_node_ids": list(impacted),
            "impacted_count": len(impacted),
            "severity": "高" if len(impacted) > 5 else "中" if len(impacted) > 2 else "低",
        }

    def get_online_nodes(self) -> list[dict[str, Any]]:
        """获取所有在线节点。"""
        return [
            row for row in store.rows(self.MODULE)
            if row.get("status") == "在线"
        ]

    # ---- 前置关系与依赖复算（供查询调度消费） ----

    def _row_by_id(self, node_id: str) -> dict[str, Any] | None:
        for row in store.rows(self.MODULE):
            if str(row.get("id")) == str(node_id):
                return row
        return None

    def _row_by_table(self, table_name: str) -> dict[str, Any] | None:
        for row in store.rows(self.MODULE):
            if str(row.get("节点名称", "")) == table_name:
                return row
        return None

    def _prerequisites_of(self, node_id: str) -> list[dict[str, Any]]:
        """返回节点的直接前置（上游）关系，未登记的上游也如实列出而不是报错。"""
        prerequisites: list[dict[str, Any]] = []
        entry = self._row_by_id(node_id)
        if entry is None:
            return prerequisites
        upstream_raw = str(entry.get("上游列表", ""))
        for up_id in [part.strip() for part in upstream_raw.split(",") if part.strip()]:
            up_row = self._row_by_id(up_id)
            prerequisites.append({
                "node_id": up_id,
                "table": str(up_row.get("节点名称", "")) if up_row else "",
                "registered": up_row is not None,
            })
        return prerequisites

    def table_prerequisites(self, target_table: str) -> dict[str, Any]:
        """血缘详情页：给出一张表（血缘节点）的前置关系。"""
        entry = self._row_by_table(target_table)
        if entry is None:
            return {
                "ok": False,
                "message": f"血缘中未登记表 {target_table}，无法提供前置关系",
                "table": target_table,
                "prerequisites": [],
            }
        prerequisites = self._prerequisites_of(str(entry.get("id")))
        return {
            "ok": True,
            "table": target_table,
            "node_id": str(entry.get("id")),
            "node_type": str(entry.get("节点类型", "")),
            "prerequisite_count": len(prerequisites),
            "prerequisites": prerequisites,
        }

    def recompute_dependency_inputs(
        self,
        targets: list[str],
        partition: str = DEFAULT_PARTITION,
    ) -> dict[str, Any]:
        """依赖复算：对每个目标表沿血缘前置关系核对必需输入是否到齐。

        同一次复算可覆盖多支链路；未在血缘登记的上游标记为 missing，
        不抛异常，由调度侧据此判定阻塞点。
        """
        results: dict[str, dict[str, Any]] = {}
        missing_dependencies: list[dict[str, str]] = []
        blocked_targets: list[str] = []
        ready_targets: list[str] = []

        for target in targets:
            entry = self._row_by_table(target)
            if entry is None:
                # 目标表本身未登记：无法核对，按阻塞处理并给出明确原因。
                results[target] = {
                    "table": target,
                    "registered": False,
                    "ready": False,
                    "blockers": [{"kind": "unregistered_table", "table": target, "node_id": ""}],
                    "available_inputs": [],
                    "missing_inputs": [],
                }
                missing_dependencies.append(
                    {"target": target, "node_id": "", "table": target, "kind": "unregistered_table"}
                )
                blocked_targets.append(target)
                continue

            prerequisites = self._prerequisites_of(str(entry.get("id")))
            available_inputs: list[dict[str, Any]] = []
            missing_inputs: list[dict[str, str]] = []
            for pre in prerequisites:
                up_table = pre["table"]
                if not pre["registered"]:
                    missing_inputs.append({
                        "node_id": pre["node_id"], "table": "", "kind": "unregistered_node"
                    })
                    missing_dependencies.append({
                        "target": target,
                        "node_id": pre["node_id"],
                        "table": "",
                        "kind": "unregistered_node",
                    })
                    continue
                output = lineage_registry.get(up_table, partition)
                if output is None:
                    missing_inputs.append({
                        "node_id": pre["node_id"], "table": up_table, "kind": "partition_not_ready"
                    })
                    missing_dependencies.append({
                        "target": target,
                        "node_id": pre["node_id"],
                        "table": up_table,
                        "kind": "partition_not_ready",
                    })
                else:
                    available_inputs.append(output.to_dict())

            ready = not missing_inputs
            results[target] = {
                "table": target,
                "node_id": str(entry.get("id")),
                "registered": True,
                "ready": ready,
                "available_inputs": available_inputs,
                "missing_inputs": missing_inputs,
                "blockers": missing_inputs if not ready else [],
            }
            (ready_targets if ready else blocked_targets).append(target)

        return {
            "ok": True,
            "partition": partition,
            "target_count": len(targets),
            "ready_tables": ready_targets,
            "blocked_tables": blocked_targets,
            "missing_dependencies": missing_dependencies,
            "tables": results,
        }

    def export_lineage_graph(self) -> dict[str, Any]:
        """导出完整血缘图结构（供数据范围消费）。"""
        graph = self.build_graph_from_store()
        adj = graph.to_adjacency()
        return {
            "ok": True,
            "node_count": len(adj["nodes"]),
            **adj,
        }

    def domain_snapshot(self) -> dict[str, Any]:
        base = super().domain_snapshot()
        base["artifact"] = "数据血缘数据集"
        online = sum(1 for row in store.rows(self.MODULE) if row.get("status") == "在线")
        base["online_nodes"] = online
        return base