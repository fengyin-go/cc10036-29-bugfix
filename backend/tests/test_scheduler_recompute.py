"""调度与血缘依赖复算的端到端回归脚本（无外部依赖，直接跑服务层）。

复现场景：
1. 清洗/汇总执行次序错位是否修复；
2. 血缘详情页前置关系与依赖复算（门店链已齐、渠道链缺一个上游）；
3. 循环依赖、未登记依赖不得执行，待执行里不残留错误就绪计划；
4. 无依赖旧计划照旧开跑；中断重试不能绕过实际依赖；
5. 加入缺前驱分支后，比较真正产出的分区与出数时刻。

运行：backend/.venv/bin/python tests/test_scheduler_recompute.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lineage_registry import DEFAULT_PARTITION, lineage_registry
from app.services import service_for
from app.store import store

# 注入可控时钟，让出数时刻可断言、可比较。
_TICKS = iter([1_700_000_000 + i for i in range(200)])
lineage_registry.clock = lambda: next(_TICKS)
lineage_registry.seed()

PASS = "[PASS]"
FAIL = "[FAIL]"
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = PASS if condition else FAIL
    print(f"{mark} {label}" + (f" —— {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def reset_scheduler_rows() -> None:
    """把调度计划恢复到初始状态，避免跨用例污染。"""
    from app.seed import SEED_ROWS

    store._tables["query_scheduler"] = [dict(row) for row in SEED_ROWS["query_scheduler"]]


def plan_id(name: str) -> int:
    for row in store.rows("query_scheduler"):
        if row.get("计划名称") == name:
            return int(row["id"])
    raise KeyError(name)


def status_of(name: str) -> str:
    return str(store.find("query_scheduler", plan_id(name)).get("status"))


def main() -> int:
    sched = service_for("query_scheduler")
    lineage = service_for("data_lineage")

    print("========== 1. 执行次序：清洗必须先于汇总 ==========")
    topo = sched.topological_order()
    order = topo["execution_order"]
    check(
        "门店销售清洗先于门店日汇总",
        order.index("门店销售清洗") < order.index("门店日汇总"),
        str(order),
    )
    check(
        "渠道订单清洗先于渠道日汇总",
        order.index("渠道订单清洗") < order.index("渠道日汇总"),
        str(order),
    )
    check("拓扑识别出循环依赖", topo["has_cycle"] is True)
    check(
        "循环计划不在执行次序中",
        set(topo["cycle_nodes"]) == {"循环任务甲", "循环任务乙"}
        and "循环任务甲" not in order and "循环任务乙" not in order,
    )
    listed, _ = sched.list_entries(page=1, size=100)
    listed_names = [row["计划名称"] for row in listed]
    check(
        "调度列表里清洗排到汇总前（次序错位修复）",
        listed_names.index("门店销售清洗") < listed_names.index("门店日汇总"),
        str(listed_names),
    )

    print()
    print("========== 2. 血缘详情页前置关系与依赖复算 ==========")
    pre = lineage.table_prerequisites("dwd_channel_order_clean")
    pre_ids = [item["node_id"] for item in pre["prerequisites"]]
    check("渠道清洗前置包含13与99", set(pre_ids) == {"13", "99"}, str(pre_ids))
    check("节点99标记为未登记", next(p for p in pre["prerequisites"] if p["node_id"] == "99")["registered"] is False)

    recompute = lineage.recompute_dependency_inputs(
        ["dwd_store_clean", "ads_store_daily_summary",
         "dwd_channel_order_clean", "ads_channel_daily_summary"]
    )
    check("门店清洗输入已齐", recompute["tables"]["dwd_store_clean"]["ready"] is True)
    channel = recompute["tables"]["dwd_channel_order_clean"]
    check(
        "渠道清洗实际阻塞点为未登记节点99",
        channel["ready"] is False
        and any(m["node_id"] == "99" and m["kind"] == "unregistered_node"
                for m in channel["missing_inputs"]),
        str(channel["missing_inputs"]),
    )
    check(
        "复算不抛错且缺失依赖被结构化返回",
        any(m["kind"] == "unregistered_node" for m in recompute["missing_dependencies"]),
    )

    print()
    print("========== 3. 待执行只含真正可执行计划 ==========")
    rc = sched.recompute_plan_dependencies()
    ready_names = [p["plan"] for p in rc["executable_plans"]]
    blocked_names = [p["plan"] for p in rc["blocked_plans"]]
    check(
        "初始可执行=门店销售清洗+前置已完成的旧计划用户画像更新",
        ready_names == ["用户画像更新", "门店销售清洗"],
        str(ready_names),
    )
    ready_rows = [row["计划名称"] for row in sched.get_ready_plans()]
    check("待执行不残留错误就绪计划（无阻塞项混入）",
          set(ready_rows) == {"用户画像更新", "门店销售清洗"}, str(ready_rows))
    check("渠道两计划、循环两计划、孤儿任务均在阻塞列",
          {"渠道订单清洗", "渠道日汇总", "循环任务甲", "循环任务乙", "孤儿汇总任务"}
          <= set(blocked_names), str(blocked_names))

    print()
    print("========== 4. 守卫：循环/缺失/未完成依赖不能执行 ==========")
    entry, message = sched.run_action(plan_id("循环任务甲"), "开始执行")
    check("循环依赖被拦截", entry is None and "循环依赖" in message, message)
    entry, message = sched.run_action(plan_id("孤儿汇总任务"), "开始执行")
    check("未登记依赖被拦截", entry is None and "未登记" in message, message)
    entry, message = sched.run_action(plan_id("门店日汇总"), "开始执行")
    check("前置未完成时汇总被拦截", entry is None and "依赖未满足" in message, message)
    check("被拦计划状态仍是待调度", status_of("门店日汇总") == "待调度")

    print()
    print("========== 5. 无依赖旧计划按原方式开跑 ==========")
    entry, message = sched.run_action(plan_id("门店销售清洗"), "开始执行")
    check("门店销售清洗可直接开始执行", entry is not None and entry["status"] == "执行中", message)
    entry, message = sched.run_action(plan_id("门店销售清洗"), "完成调度")
    check("门店销售清洗可完成", entry is not None and entry["status"] == "已完成", message)

    print()
    print("========== 6. 完成后分区产出与下游解锁 ==========")
    ledger = sched.execution_ledger()
    store_output = next((o for o in ledger["outputs"] if o["table"] == "dwd_store_clean"), None)
    check("门店清洗产出分区已登记", store_output is not None
          and store_output["partition"] == DEFAULT_PARTITION
          and store_output["source_plan"] == "门店销售清洗", str(store_output))
    rc2 = sched.recompute_plan_dependencies()
    ready_after = [p["plan"] for p in rc2["executable_plans"]]
    check("门店日汇总在清洗出数后变为可执行", "门店日汇总" in ready_after, str(ready_after))
    check("渠道链路仍被缺失上游阻塞",
          "渠道订单清洗" in [p["plan"] for p in rc2["blocked_plans"]])

    entry, _ = sched.run_action(plan_id("门店日汇总"), "开始执行")
    check("门店日汇总此时可开跑", entry is not None and entry["status"] == "执行中")
    entry, _ = sched.run_action(plan_id("门店日汇总"), "完成调度")
    check("门店日汇总可完成", entry is not None and entry["status"] == "已完成")

    print()
    print("========== 7. 出数台账：真实分区与出数时刻比较 ==========")
    ledger = sched.execution_ledger()
    clean_out = next(o for o in ledger["outputs"] if o["table"] == "dwd_store_clean")
    summary_out = next(o for o in ledger["outputs"] if o["table"] == "ads_store_daily_summary")
    check("汇总出数时刻晚于清洗", summary_out["produced_at"] > clean_out["produced_at"],
          f"clean={clean_out['produced_at']} summary={summary_out['produced_at']}")
    check("渠道表没有任何产出分区",
          not any(o["table"].startswith("dwd_channel") or o["table"].startswith("ads_channel")
                  for o in ledger["outputs"]))

    print()
    print("========== 8. 失败重试不能绕过实际依赖 ==========")
    reset_scheduler_rows()
    retry = sched.retry_failed()
    weekly = store.find("query_scheduler", plan_id("周报汇总计算"))
    check("周报汇总因前置未完成无法重试",
          retry["retried_count"] == 0
          and any(item["plan"] == "周报汇总计算" for item in retry["blocked"])
          and weekly["status"] == "调度失败",
          str(retry))
    # 补齐前置后重试才放行，证明守卫依据真实依赖而非重试动作本身。
    sched.run_action(plan_id("交易立方刷新"), "完成调度")
    sched.run_action(plan_id("用户画像更新"), "开始执行")
    # 用户画像更新为UPDATE语句、无血缘目标表，前置完成后即可执行
    sched.run_action(plan_id("用户画像更新"), "完成调度")
    retry = sched.retry_failed()
    check("前置补齐后重试放行",
          retry["retried_count"] == 1 and status_of("周报汇总计算") == "执行中", str(retry))
    entry, message = sched.run_action(plan_id("渠道订单清洗"), "开始执行")
    check("渠道清洗依旧被缺失上游拦截", entry is None and "未登记" in message, message)

    print()
    print("========== 9. 调度详情页标出阻塞点 ==========")
    reset_scheduler_rows()
    detail = sched.plan_detail(plan_id("渠道订单清洗"))
    check("渠道清洗详情标记不可执行", detail["executable"] is False)
    check("详情阻塞点指向节点99",
          any("99" in b["detail"] for b in detail["blockers"]), str(detail["blockers"]))
    detail_store = sched.plan_detail(plan_id("门店销售清洗"))
    check("门店清洗详情标记可执行且无阻塞",
          detail_store["executable"] is True and detail_store["blockers"] == [])

    print()
    if failures:
        print(f"共 {len(failures)} 项失败：{failures}")
        return 1
    print("全部用例通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
