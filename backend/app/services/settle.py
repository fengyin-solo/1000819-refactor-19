"""作业结算业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.services.damage_rule import assess_damage
from app.store import store

MODULE = "settle"
REQUIRED_FIELDS = ["结算单号", "结算对象", "结算周期"]
OPTIONAL_FIELDS = ["关联残损编号"]
STATUS_ORDER = ["待核对", "核对中", "已确认", "已收款", "有争议"]
ACTION_RULES = {"发起核对": "核对中", "确认结算": "已收款", "标记争议": "有争议"}
NEGATIVE_ACTIONS = []


class SettleService:
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
            rows = [row for row in rows if keyword in str(row.get("结算单号", ""))]
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
        for field in OPTIONAL_FIELDS:
            if str(values.get(field) or "").strip():
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"结算单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于作业结算可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        message = f"结算单已{action}"
        if action in ("发起核对", "确认结算"):
            liable = self._resolve_liable_party(entry)
            if liable:
                message += f"，费用承担方：{liable}"
        return entry, message

    def _resolve_liable_party(self, entry: dict[str, Any]) -> str | None:
        """残损费用的承担方：与残损登记、集装箱档案共用同一个判定，不自行解释。

        结算单带「关联残损编号」时，把对应残损记录交给共享判定，
        结论写回结算单的「费用承担方」；没有关联或残损单不存在时不动。
        """
        damage_no = str(entry.get("关联残损编号") or "").strip()
        if not damage_no:
            return None
        damage = next(
            (row for row in store.rows("damage") if str(row.get("残损编号")) == damage_no),
            None,
        )
        if damage is None:
            return None
        liable = assess_damage(damage).费用承担方
        entry["费用承担方"] = liable
        return liable
