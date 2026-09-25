"""集装箱档案业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.services.damage_rule import DamageAssessment
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

    def apply_damage_assessment(self, container_no: str, assessment: DamageAssessment) -> str:
        """把残损共享判定的箱况联动结论落到集装箱档案。

        本方法只负责落地，不做任何判定；箱况改不改、改成什么，
        一律以 app.services.damage_rule.assess_damage 的结论为准。
        历史箱况不被回写：只有定责动作触发时才会走到这里。
        """
        if not assessment.箱况联动:
            return "箱况不变"
        for row in store.rows(MODULE):
            if str(row.get("箱号")) == container_no:
                row["箱况等级"] = assessment.箱况等级
                row["箱体状态"] = assessment.箱体状态
                return f"箱况等级→{assessment.箱况等级}、箱体状态→{assessment.箱体状态}"
        return "未找到关联集装箱，箱况未变更"
