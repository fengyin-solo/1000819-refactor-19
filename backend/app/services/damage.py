"""残损登记业务规则：状态流转、字段校验与筛选口径都收在这里。

责任方判定与箱况联动不在本模块各自判断，统一走 damage_assessment.assess_damage。
"""
from __future__ import annotations

from typing import Any

from app.services.container import ContainerService
from app.services.damage_assessment import DamageVerdict, assess_damage
from app.store import store

MODULE = "damage"
REQUIRED_FIELDS = ["残损编号", "关联箱号", "残损类型"]
STATUS_ORDER = ["待定责", "已定责", "处理中", "已闭环", "已挂起"]
ACTION_RULES = {"确认定责": "已定责", "提交闭环": "已闭环", "挂起记录": "已挂起"}
NEGATIVE_ACTIONS = []


class DamageService:
    def __init__(self) -> None:
        self._containers = ContainerService()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("残损编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def get_verdict(self, entry_id: int) -> DamageVerdict | None:
        """残损登记侧读取统一判定：责任方归属与箱况联动结论。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return assess_damage(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"残损记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于残损登记可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        message = f"残损记录已{action}"
        if action == "确认定责":
            # 责任方与箱况联动都取统一判定的结论，先判定再落状态
            verdict = assess_damage(entry)
            entry["责任方"] = verdict.responsible
            linked = self._containers.apply_damage_verdict(str(entry.get("关联箱号") or ""), verdict)
            message = f"残损记录已{action}：{verdict.basis}"
            if verdict.condition_grade and linked is None:
                message += "；关联箱号未建档，箱况未联动"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, message
