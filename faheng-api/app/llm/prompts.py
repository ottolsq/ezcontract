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
      "suggestion": "完整、可直接整段替换原条款的条款文本",
      "sub_item_no": "5.3"
    }
  ]
}"""

# 条款子项编号提示：LLM 引用具体 X.Y 子项时输出该编号，否则留空字符串。
SUBITEM_NO_HINT = (
    'sub_item_no 字段：如果风险针对条款中某个 X.Y 子项（如 5.1 / 5.3），'
    '必须输出该子项编号字符串（例如 "5.3"）；如果风险针对整个条款、'
    '或无法确定具体子项，输出空字符串 ""。\n'
    "不要编造不存在的子项编号；只输出该条款正文里真实出现过的 X.Y。\n"
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
) -> list[dict]:
    """审查 prompt：skill 知识库 + ERP 规则库 + 本批条款 + JSON schema + 硬性约束"""
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
    user_parts.append(
        f"## 任务\n逐条对照以上参考与规则库识别风险条款，输出 JSON（risks 为数组，未发现风险时为空数组）：\n{RISK_SCHEMA_HINT}"
    )
    user_parts.append(f"## 子项编号\n{SUBITEM_NO_HINT}")
    user_parts.append(
        "## 硬性约束\n"
        "1. clause_id 只能取自上述编号，不得编造\n"
        "2. matched_rules 只能引用规则库中的规则号；确有风险但规则库未覆盖时可为空数组\n"
        "3. suggestion 必须是完整条款文本（不是修改意见），将直接整段替换原条款\n"
        "4. 未命中风险的条款不要输出；宁缺勿滥，不确定的不输出\n"
        "5. 每个 JSON 对象必须完整闭合；若条款较多，只输出最重要的风险项\n"
        "6. level 仅使用 high / medium / low（与现有 schema 保持一致）；若内部按 P0/P1/P2 思考，请先映射：P0=high, P1=medium, P2=low\n"
        "7. issue/impact 用简体中文"
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
