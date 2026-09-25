"""残损定责与箱况联动：全系统唯一的判定入口。

残损登记、集装箱档案、作业结算三处都从 ``assess_damage`` 拿结论，
任何模块不得再各自写一份责任方或箱况联动逻辑；要调整规则只改这里。

判定是纯函数：同一条残损记录，在任何模块、任何时刻判出的结果一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# 责任方取值全集，三处展示与流转都以此为准。
LIABLE_PARTIES = ("船方", "货方", "港方", "待定")

# 残损类型 -> 责任方：全系统唯一一份映射。
_TYPE_LIABILITY = {
    "装卸损伤": "港方",
    "运输损伤": "船方",
    "货物自损": "货方",
    "自然锈蚀": "船方",
}

# 残损类型 -> 定责后的箱况联动（目标箱况等级, 目标箱体状态）；
# 不在表内的类型表示箱况不跟着改。箱体状态取值与集装箱档案状态序列一致。
_TYPE_CONDITION = {
    "装卸损伤": ("C", "待修"),
    "运输损伤": ("C", "待修"),
    "自然锈蚀": ("B", "待检"),
}


@dataclass(frozen=True)
class DamageAssessment:
    """一次残损判定的结论：责任方怎么定、箱况要不要跟着改。"""

    责任方: str
    箱况联动: bool
    箱况等级: str | None
    箱体状态: str | None

    @property
    def 费用承担方(self) -> str:
        """结算口径与定责口径同源：谁担责，残损费用就向谁结算。"""
        return self.责任方


def assess_damage(entry: Mapping[str, Any]) -> DamageAssessment:
    """对一条残损记录给出责任方与箱况联动结论。

    已定责的记录（责任方已是有效责任方）沿用记录值，历史判定不翻案；
    未定的按残损类型映射，未认识的类型判「待定」且箱况不动。
    """
    recorded = str(entry.get("责任方") or "").strip()
    damage_type = str(entry.get("残损类型") or "").strip()
    if recorded in LIABLE_PARTIES and recorded != "待定":
        liable = recorded
    else:
        liable = _TYPE_LIABILITY.get(damage_type, "待定")
    condition = _TYPE_CONDITION.get(damage_type)
    if condition is None:
        return DamageAssessment(责任方=liable, 箱况联动=False, 箱况等级=None, 箱体状态=None)
    return DamageAssessment(责任方=liable, 箱况联动=True, 箱况等级=condition[0], 箱体状态=condition[1])
