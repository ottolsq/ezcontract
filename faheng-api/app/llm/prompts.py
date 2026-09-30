"""Prompt 构造：审查 / 起草 / 修订"""
from __future__ import annotations

from app.schemas.draft import DraftGenerateIn
from app.services.rules import Rule, get_rules
from app.services.skill_refs import get_skill_references

REVIEW_SYSTEM = (
    "你是一名资深企业法务，默认立场为甲方（采购方/委托方）。\n"
    "你必须严格遵循给定的《审查框架》进行三层（宏观-中观-微观）四步（澄清-扫描-落地-复核）合同审查：\n"
    "1) 先用《审查框架》的通用风险清单扫描合同结构与高风险条款；\n"
    "2) 再用《合同类型路由》和《优先审查条款》核对当前合同类型下的高风险条款；\n"
    "3) 必要时从《条款库》抽取可直接整段替换原条款的规范措辞；\n"
    "4) 最后仍要对照《审核规则库》逐条确认 ERP 软件采购类条款是否有遗漏。\n"
    "只输出 JSON，不输出任何解释、markdown 代码块或其他文本。"
)

RISK_SCHEMA_HINT = """{
  "risks": [
    {
      "clause_id": "C01",
      "title": "风险短标题（10字以内）",
      "level": "high",
      "matched_rules": ["ERP-PAY-001"],
      "issue": "风险说明，80字以内",
      "impact": "对甲方的影响，80字以内",
      "suggestion": "完整、可直接整段替换原条款的条款文本（replace 时必填）",
      "sub_item_no": "5.3",
      "operation": "replace | insert_after | insert_before | delete",
      "anchor_clause_id": "C01",
      "anchor_sub_item_no": "5.2",
      "new_clause_no": "第十二条",
      "new_clause_title": "数据安全与保密"
    }
  ]
}"""

# Plan A 后续：N 级嵌套子项 + 编号剥离
SUBITEM_NO_HINT = (
    "sub_item_no 字段：必须输出待审查子项的真实 internal_no（半角规范化形式）。\n"
    "取值范围由本批输入中的 subitems 列表给出（每条形如 3.1、3.1(1)、3.2(a)、7.2(2)）；"
    "禁止编造不在列表中的 internal_no。\n"
    "针对整条款且范围未知时输出空字符串 ""。\n"
    "## suggestion 编号剥离（Plan A 硬性约束）\n"
    "replace / insert_* / modify 操作：suggestion 不得携带子项编号前缀。\n"
    "例：针对 7.2(1) 的 replace，suggestion 写「逾期支付租金的，每逾期一日按应付租金的 5% 向甲方支付违约金…」即可，"
    "系统会自动按原文「（1）」前缀拼接回 docx；不要在 suggestion 里写「（1）逾期…」。\n"
    "针对 X.Y 整子项的 replace，suggestion 不要以「3.1」开头；写正文即可，系统会自动拼回「3.1」。\n"
    "## 括号规范\n"
    "中文合同正文统一使用全角中文括号「（Z）」；禁止在 suggestion 正文里使用半角数字编号括号 (1)、(2)、(3)。\n"
)

# Plan B：编辑操作语义
OPERATION_HINT = (
    "operation 字段含义（Plan B 精确编辑指令，默认 replace，向后兼容旧输出）：\n"
    "- replace: 替换 clause_id（+必填 sub_item_no）对应的单位。"
    "suggestion 只写该单位正文（不含编号前缀），系统会自动按原文 display_no 拼回。\n"
    "- insert_after / insert_before: 在 anchor_clause_id（+可选 anchor_sub_item_no）对应单位的后/前"
    "插入新单位。suggestion 必须以新编号 + 全角分隔符开头（如「（4）…」或「3.3 」），"
    "由系统校验编号合法并写入。新增整条款时建议同时给出 new_clause_no 与 new_clause_title。\n"
    "- delete: 删除 clause_id（+可选 sub_item_no）对应的单位；suggestion 可留空。\n"
    "每个风险对象只能描述一个被修改单位，禁止一次替换多个子项。\n"
    "anchor_clause_id / clause_id 只能取自待审查条款列表中的真实 id；不要编造。\n"
    "## suggestion 编号剥离约束（Plan A 升级）\n"
    "replace / modify 时 suggestion 不得携带子项编号前缀（不写「3.1」「（1）」等开头）。"
    "系统会根据 sub_item_no 找到目标 display_no 并自动补回；"
    "insert_* 时由系统生成新编号，suggestion 必须以新编号开头；"
    "delete 时 suggestion 可为空。\n"
)


def _format_rules(rules: list[Rule]) -> str:
    lines = []
    for r in rules:
        lines.append(f"{r.rule_id} | {r.title} | 等级:{r.level}")
        lines.append(f"  触发条件：{r.trigger}")
        lines.append(f"  建议条款：{r.suggestion}")
    return "\n".join(lines)


def _truncate(text: str, limit: int = 6000) -> str:
    """长参考文档截断，避免一次性塞太多 token"""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n（参考文档过长，已截断，请按当前 batch 条款相关性选用）"


def build_review_prompt(
    clauses_text: str,
    contract_type: str | None = None,
    subitems_index: str = "",
) -> list[dict]:
    """审查 prompt：skill 知识库 + 规则库 + 本批条款（含 subitems 列表）+ JSON schema + 硬性约束。

    `subitems_index` 形如：
        C03 → 3.1, 3.1(1), 3.1(2), 3.2, 3.2(a), 3.2(b), 3.2(c), 3.3
        C07 → 7.1, 7.1(1), 7.1(2), 7.2, 7.2(1), 7.2(2), 7.2(3)
    给 LLM 提供完整 sub_item_no 取值范围，禁止编造。
    """
    rules = get_rules()
    refs = get_skill_references(contract_type)

    sections: list[str] = []
    if refs["review_framework"]:
        sections.append(f"## 审查框架（三层 / 四步 / 通用风险清单）\n{_truncate(refs['review_framework'], 6000)}")
    if refs["contract_routing"]:
        sections.append(f"## 合同类型路由\n{_truncate(refs['contract_routing'], 4000)}")
    if refs["priority_clauses"]:
        sections.append(f"## 优先审查条款\n{_truncate(refs['priority_clauses'], 3000)}")
    if refs["clause_library"]:
        sections.append(f"## 推荐条款库（参考措辞，按需选用）\n{_truncate(refs['clause_library'], 6000)}")
    if refs["contract_type_ref"]:
        sections.append(f"## 当前合同类型专项参考\n{_truncate(refs['contract_type_ref'], 4000)}")
    if contract_type:
        sections.append(f"（当前合同类型提示：{contract_type}）")

    user_parts = ["\n\n".join(sections)] if sections else []
    user_parts.append(
        f"## 既有审核规则库（共{len(rules)}条，全部规则如下）\n{_format_rules(rules)}"
    )
    user_parts.append(
        "## 待审查条款（clause_id 为条款唯一编号，输出时必须原样引用）\n"
        + clauses_text
    )
    if subitems_index:
        user_parts.append(
            "## 子项索引（sub_item_no 取值集合；输出 sub_item_no 时只能从下列中选，禁止编造）\n"
            + subitems_index
        )
    user_parts.append(
        f"## 任务\n逐条对照以上参考与规则库识别风险条款，输出 JSON（risks 为数组，未发现风险时为空数组）：\n{RISK_SCHEMA_HINT}"
    )
    user_parts.append(f"## 子项编号\n{SUBITEM_NO_HINT}")
    user_parts.append(f"## 编辑操作\n{OPERATION_HINT}")
    user_parts.append(
        "## 硬性约束\n"
        "1. clause_id 只能取自上述编号，不得编造\n"
        "2. matched_rules 只能引用规则库中的规则号；确有风险但规则库未覆盖时可为空数组\n"
        "3. 未命中风险的条款不要输出；宁缺勿滥，不确定的不输出\n"
        "4. 每个 JSON 对象必须完整闭合；若条款较多，只输出最重要的风险项\n"
        "5. level 仅使用 high / medium / low（与现有 schema 保持一致）；若内部按 P0/P1/P2 思考，请先映射：P0=high, P1=medium, P2=low\n"
        "6. issue/impact 用简体中文\n"
        "7. Plan B 编辑约束：每个风险只代表一个被修改单位；\n"
        "   - replace 且 sub_item_no 非空时，suggestion **不得携带编号前缀**（不写「3.1」「（1）」），仅写正文；系统会按原文 display_no 自动拼回；\n"
        "   - replace 且 sub_item_no 为空（整条款）时，suggestion 也只写整条款正文，且不得在文本里携带 X.Y 子项编号（禁止把多个子项打包）；\n"
        "   - insert_* 必须给出 anchor_clause_id，suggestion 必须以新编号 + 全角分隔符开头；\n"
        "   - delete 必须引用真实存在的 clause_id 或 sub_item_no\n"
        "8. 中文合同正文统一使用全角中文括号「（Z）」；禁止在 suggestion 正文里使用半角数字编号括号 (1)、(2)、(3)，否则与原合同版式不一致\n"
    )
    user = "\n\n".join(user_parts)
    return [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": user},
    ]


DRAFT_SYSTEM = "你是资深合同起草专家，擅长生成结构规范、条款完备的中文商务合同模板。"


def build_draft_prompt(req: DraftGenerateIn) -> list[dict]:
    party_a = req.party_a or "【甲方名称】"
    party_b = req.party_b or "【乙方名称】"
    user = f"""请根据以下需求起草一份合同模板：
- 关键词：{req.keywords}
- 合同类型：{req.contract_type or "根据关键词自行判断"}
- 甲方：{party_a}；乙方：{party_b}
- 补充要求：{req.extra_requirements or "无"}

## 要求
1. 输出 Markdown，层级只用四级：
   - 一级标题（#）为合同名称
   - 二级标题（##）为「第X条」条款
   - 三级标题（###）为条款内的子项「X.Y」（如 3.1、3.2），用于条款内容确实需要分点的情况
   - 四级标题（####）为 X.Y 子项下的嵌套条目，**必须**使用「（1）/（2）/（3）」或「（a）/（b）/（c）」格式，**禁止**使用 X.Y.Z 格式（如 3.1.1）
2. 子项规则：仅当条款内容确实需要分点（如付款阶段、验收步骤、多类义务）时才用三级标题"X.Y"（如 3.1、3.2），每个子项下再写正文或（1）/（a）形式的嵌套条目；简单条款直接用段落或列表，不要为了分层而分层
3. 同一个父 h3 下的嵌套条目形式必须统一：要么全部用（1）（2），要么全部用（a）（b），不要混用
4. 结构完整：鉴于条款、定义、标的与范围、价款与支付、交付与验收、双方权利义务、违约责任、保密、知识产权、不可抗力、争议解决、其他约定、签署栏
5. 不确定的信息用占位符，如【金额】【日期】
6. 立场均衡但默认保护甲方（采购方）利益
7. 不要使用 Markdown 表格

## 输出格式
只输出 JSON（不要代码块围栏）：
{{"title": "合同名称", "markdown": "# 合同名称\\n...全文..."}}"""
    return [
        {"role": "system", "content": DRAFT_SYSTEM},
        {"role": "user", "content": user},
    ]


def build_revise_prompt(current_markdown: str, instruction: str) -> list[dict]:
    user = f"""以下是当前合同草稿（Markdown）：
{current_markdown}

用户修改要求：{instruction}

请输出修改后的完整合同。保持原有结构与编号体系：
- 一级 = 合同名
- 二级 = 第X条（##）
- 三级 = X.Y 子项（###）
- 四级 = X.Y 下的嵌套条目（####），**必须**用（1）/（2）或（a）/（b）格式，**禁止**使用 X.Y.Z 格式
- 同一父 h3 下的嵌套条目形式统一，要么全数字要么全字母

只改动需要改动的部分，其余条款原文保留。不要使用 Markdown 表格。

只输出 JSON（不要代码块围栏）：
{{"title": "合同名称", "markdown": "# 合同名称\\n...全文..."}}"""
    return [
        {"role": "system", "content": DRAFT_SYSTEM},
        {"role": "user", "content": user},
    ]


# ── 履约节点提取 ──

COMPLIANCE_SYSTEM = (
    "你是合同履约节点提取助手。从候选条款中提取所有带时间约束的履约义务，"
    "把相对时间（签署后N日 / 每期开始前N日 / 终止后N年）转换为「锚点 + 偏移」结构，"
    "具体日期由系统代码计算，你绝不自己做日期加减。只输出 JSON，"
    "不输出任何解释、markdown 代码块或其他文本。"
)

COMPLIANCE_SCHEMA_HINT = """{
  "meta": {
    "sign_date": "2026-09-28",
    "contract_start": "2026-10-01",
    "contract_end": "2028-09-30"
  },
  "nodes": [
    {
      "ref": "C04#4.1(2)",
      "node_type": "payment",
      "title": "支付季度租金",
      "description": "每季度初前7日内支付当期租金4200元/月",
      "anchor": "contract_start",
      "anchor_date": "",
      "offset_days": -7,
      "offset_months": 0,
      "recurring": "quarterly",
      "needs_review": false
    },
    {
      "ref": "C04#4.2(1)",
      "node_type": "deposit",
      "title": "支付押金",
      "description": "签署后3日内支付押金8400元",
      "anchor": "sign_date",
      "anchor_date": "",
      "offset_days": 3,
      "offset_months": 0,
      "recurring": "none",
      "needs_review": false
    }
  ]
}"""


def build_compliance_prompt(
    candidates_text: str,
    meta_lines: str = "",
) -> list[dict]:
    """履约提取 prompt：候选条款（带 ref）+ 元信息行 + schema + 硬性约束。"""
    user_parts: list[str] = []
    user_parts.append(
        "## 候选条款（ref 为候选唯一编号，输出时必须原样引用，禁止编造）\n"
        + candidates_text
    )
    if meta_lines:
        user_parts.append("## 合同元信息（仅供提取 meta，不作为节点来源）\n" + meta_lines)
    user_parts.append(
        "## 任务\n"
        "从候选条款中提取所有带时间约束的履约义务（付款/押金/交付/验收/到期/通知等），"
        "输出 JSON（nodes 为数组，无合适节点时为空数组）：\n" + COMPLIANCE_SCHEMA_HINT
    )
    user_parts.append(
        "## 硬性约束\n"
        "1. ref 只能取自候选列表中的编号，每个 ref 至多输出一个节点\n"
        "2. 只输出带时间约束的义务节点；纯定义（如「租金指…」）、无期限义务不输出；"
        "违约金/解除权等救济条款不是履约义务，不输出\n"
        "3. anchor 语义：absolute=条款里有明确日期（anchor_date 原样抄 YYYY-MM-DD）；"
        "sign_date=自签署日起算；contract_start=自合同起始日起算；contract_end=自合同到期/终止日起算\n"
        "4. 「每期开始前N日内支付」→ anchor=contract_start + offset_days=-N + recurring=周期；"
        "「签署后N日内」→ anchor=sign_date + offset_days=N\n"
        "5. 「终止后N年/月」→ anchor=contract_end + offset_months 换算为月（2年=24）\n"
        "6. 依赖未来事件（验收后、通知后、交接后）无法定具体日期 → needs_review=true\n"
        "7. meta 三字段提取不到就留空字符串，不要编造\n"
        "8. title 用简体中文，12 字以内；node_type 用英文枚举\n"
        "9. 只输出 JSON，确保所有括号引号完整闭合\n"
    )
    return [
        {"role": "system", "content": COMPLIANCE_SYSTEM},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
