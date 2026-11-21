"""血缘输入可用性登记表：记录每张表已产出的分区及出数时刻。

调度复算时由数据血缘服务读取，判断某张表的必需输入是否已经到齐；
调度计划「完成调度」时把产出分区回写到这里，形成可核对的出数台账。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# 当前复算批次的默认分区；两支链路都围绕这个日分区核对输入。
DEFAULT_PARTITION = "dt=2026-11-21"


@dataclass
class PartitionOutput:
    """一张表在某个分区上的一次产出。"""

    table: str
    partition: str
    produced_at: float
    source_plan: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "partition": self.partition,
            "produced_at": self.produced_at,
            "produced_at_text": _format_ts(self.produced_at),
            "source_plan": self.source_plan,
        }


def _format_ts(epoch: float) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


class LineageRegistry:
    """表 -> 已产出分区列表 的内存登记表（单例，跨服务共享）。"""

    def __init__(self) -> None:
        self._outputs: dict[str, list[PartitionOutput]] = {}
        self.clock = time.time
        self.seed()

    def seed(self) -> None:
        """灌入根节点已就绪的日分区；渠道归因源头故意缺席，用于复现缺上游。"""
        self._outputs.clear()
        base = self.clock() - 3600
        ready_roots = [
            ("ods_user_behavior_raw", "每日行为数据ETL"),
            ("ods_store_trade_daily", "门店销售清洗"),
            ("ods_channel_exposure_daily", "渠道订单清洗"),
        ]
        for offset, (table, plan) in enumerate(ready_roots):
            self.register_output(
                table,
                DEFAULT_PARTITION,
                source_plan=plan,
                produced_at=base + offset * 60,
            )

    def reset(self) -> None:
        self.seed()

    def register_output(
        self,
        table: str,
        partition: str,
        source_plan: str = "",
        produced_at: float | None = None,
    ) -> PartitionOutput:
        """登记一次表分区产出；同表同分区重复登记时刷新出数时刻。"""
        moment = produced_at if produced_at is not None else self.clock()
        bucket = self._outputs.setdefault(table, [])
        for output in bucket:
            if output.partition == partition:
                output.produced_at = moment
                output.source_plan = source_plan or output.source_plan
                return output
        output = PartitionOutput(
            table=table, partition=partition, produced_at=moment, source_plan=source_plan
        )
        bucket.append(output)
        return output

    def get(self, table: str, partition: str | None = None) -> PartitionOutput | None:
        bucket = self._outputs.get(table, [])
        if partition is None:
            return bucket[-1] if bucket else None
        for output in bucket:
            if output.partition == partition:
                return output
        return None

    def is_available(self, table: str, partition: str | None = None) -> bool:
        return self.get(table, partition) is not None

    def available_tables(self, partition: str | None = None) -> dict[str, PartitionOutput]:
        """当前已具备输入的表（指定分区时只返回该分区有产出的表）。"""
        result: dict[str, PartitionOutput] = {}
        for table, bucket in self._outputs.items():
            output = self.get(table, partition)
            if output is not None:
                result[table] = output
        return result

    def ledger(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for table in sorted(self._outputs):
            for output in self._outputs[table]:
                items.append(output.to_dict())
        return items


lineage_registry = LineageRegistry()
