"""集装箱档案业务规则：状态流转、字段校验与筛选口径都收在这里。

残损引起的箱况变化不在本模块各自判断，统一由 damage_assessment 的判定结论驱动。
"""
from __future__ import annotations

from typing import Any

from app.services.damage_assessment import DamageVerdict, assess_damage, downgrade_only
from app.store import store

MODULE = "container"
REQUIRED_FIELDS = ["箱号", "箱型", "箱况等级"]
STATUS_ORDER = ["待检", "可周转", "待修", "已报废"]
ACTION_RULES = {"登记检验": "可周转", "标记可周转": "待修", "报废箱体": "已报废"}
NEGATIVE_ACTIONS = []


class ContainerService:
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
            rows = [row for row in rows if keyword in str(row.get("箱号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def apply_damage_verdict(self, container_no: str, verdict: DamageVerdict) -> dict[str, Any] | None:
        """按统一判定联动箱况：只降不升；判定未要求联动时保持原样。"""
        row = self._find_by_no(container_no)
        if row is None:
            return None
        if verdict.condition_grade and downgrade_only(str(row.get("箱况等级") or ""), verdict.condition_grade):
            row["箱况等级"] = verdict.condition_grade
        if verdict.container_status and verdict.container_status in STATUS_ORDER:
            row["status"] = verdict.container_status
            row["pending"] = verdict.container_status != STATUS_ORDER[-1]
        return row

    def damage_verdicts(self, entry_id: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """集装箱档案侧读取统一判定：该箱关联残损单的责任方与箱况联动结论。"""
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, []
        container_no = str(row.get("箱号") or "")
        related = [item for item in store.rows("damage") if str(item.get("关联箱号") or "") == container_no]
        return row, [assess_damage(item).as_dict() for item in related]

    def _find_by_no(self, container_no: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("箱号") or "") == container_no:
                return row
        return None

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
            return None, f"集装箱 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于集装箱档案可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"集装箱已{action}"
