"""残损统一判定：责任方归属与箱况联动的唯一判断来源。

残损登记、集装箱档案、作业结算三处共用本模块的 assess_damage，
同一张残损单在任何地方得到的责任方与箱况处置都一致。

约定：
- 已定责的残损单以单据上记录的责任方为准，既有数据不回改、不重判；
- 待定责的残损单由 RESPONSIBILITY_RULES 预判，确认定责时把结论写回单据；
- 箱况联动只降不升，历史箱况不被静默改写。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

# 箱况等级序列（优 → 差），联动只允许向后（降级）移动
GRADE_ORDER = ["A", "B", "C", "D"]

# 责任方判定规则：（残损类型关键词, 残损部位关键词, 责任方）
# 关键词为空元组表示不限；按顺序匹配，先中先得
RESPONSIBILITY_RULES: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    (("装卸",), (), "码头作业方"),
    (("碰撞", "运输"), (), "承运车队"),
    (("水湿", "渗漏"), (), "船公司"),
    (("油污",), (), "货主"),
    (("锈蚀", "自然"), (), "船公司"),
]
DEFAULT_RESPONSIBLE = "待协商"

# 箱况联动规则：残损类型关键词 → (目标箱况等级, 联动箱体状态)
# 箱体状态为 None 表示只调箱况等级、不动状态；都不命中则维持现状
CONDITION_RULES: list[tuple[tuple[str, ...], str, str | None]] = [
    (("破损", "变形", "碰撞", "泄漏", "断裂"), "D", "待修"),
    (("凹陷", "裂痕", "故障"), "C", "待修"),
    (("划痕", "锈蚀", "油污"), "B", None),
]


@dataclass(frozen=True)
class DamageVerdict:
    """一张残损单的统一判定结论：三个模块都以此为准。"""

    damage_no: str
    responsible: str  # 责任方（唯一结论）
    decided: bool  # True 表示采用单据已定责的既有结论
    condition_grade: str | None  # 需联动到的箱况等级；None 表示维持
    container_status: str | None  # 需联动到的箱体状态；None 表示维持
    basis: str  # 判定依据，三处展示同一句话

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hit(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _condition_for(damage_type: str) -> tuple[str | None, str | None]:
    """按残损类型给出箱况联动结果；未命中规则时维持不变。"""
    for keys, grade, box_status in CONDITION_RULES:
        if _hit(damage_type, keys):
            return grade, box_status
    return None, None


def assess_damage(entry: Mapping[str, Any]) -> DamageVerdict:
    """对一张残损单给出唯一判定：责任方归属 + 箱况是否联动。

    已定责单据的责任方以单据记录为准（既有结论不回改）；
    箱况联动是残损类型本身的客观结果，已定责前后结论一致，
    由集装箱档案侧的只降不升逻辑保证重复执行不产生副作用。
    """
    damage_no = str(entry.get("残损编号") or "")
    damage_type = str(entry.get("残损类型") or "")
    condition_grade, container_status = _condition_for(damage_type)
    stored = str(entry.get("责任方") or "").strip()
    if entry.get("status") != "待定责" and stored:
        basis = f"残损单已定责，责任方以单据记录的「{stored}」为准"
        if condition_grade:
            basis += f"；箱况按残损类型复核联动至{condition_grade}（只降不升）"
        return DamageVerdict(
            damage_no=damage_no,
            responsible=stored,
            decided=True,
            condition_grade=condition_grade,
            container_status=container_status,
            basis=basis,
        )

    damage_part = str(entry.get("残损部位") or "")
    responsible = DEFAULT_RESPONSIBLE
    for type_keys, part_keys, party in RESPONSIBILITY_RULES:
        if _hit(damage_type, type_keys) and (not part_keys or _hit(damage_part, part_keys)):
            responsible = party
            break

    basis = f"按残损类型「{damage_type or '未填'}」判定责任方为{responsible}"
    if condition_grade is None:
        basis += "，箱况维持不变"
    else:
        basis += f"，箱况等级联动至{condition_grade}"
    return DamageVerdict(
        damage_no=damage_no,
        responsible=responsible,
        decided=False,
        condition_grade=condition_grade,
        container_status=container_status,
        basis=basis,
    )


def downgrade_only(current: str, target: str) -> bool:
    """箱况等级从 current 调到 target 是否属于降级；未入序列的旧等级允许定级一次。"""
    if current not in GRADE_ORDER:
        return target in GRADE_ORDER
    if target not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(target) > GRADE_ORDER.index(current)
