"""Prompt 构造：审查 / 起草 / 修订"""
from __future__ import annotations

from app.schemas.draft import DraftGenerateIn
from app.services.rules import Rule, get_rules

REVIEW_SYSTEM = (
    "你是一名资深企业法务，立场为甲方（采购方），负责审查ERP软件采购类合同。"
    "你的任务是严格按给定的《审核规则库》逐条对照合同条款识别风险。"
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
      "suggestion": "完整、可直接整段替换原条款的条款文本"
    }
  ]
}"""


def _format_rules(rules: list[Rule]) -> str:
    lines = []
    for r in rules:
        lines.append(f"{r.rule_id} | {r.title} | 等级:{r.level}")
        lines.append(f"  触发条件：{r.trigger}")
        lines.append(f"  建议条款：{r.suggestion}")
    return "\n".join(lines)


def build_review_prompt(clauses_text: str) -> list[dict]:
    """审查 prompt：规则库全量注入 + 本批条款 + JSON schema + 硬性约束"""
    rules = get_rules()
    user = f"""## 审核规则库（共{len(rules)}条，全部规则如下）
{_format_rules(rules)}

## 待审查条款（clause_id 为条款唯一编号，输出时必须原样引用）
{clauses_text}

## 任务
逐条对照规则库识别风险条款，输出 JSON（risks 为数组，未发现风险时为空数组）：
{RISK_SCHEMA_HINT}

## 硬性约束
1. clause_id 只能取自上述编号，不得编造
2. matched_rules 只能引用规则库中的规则号；确有风险但规则库未覆盖时可为空数组
3. suggestion 必须是完整条款文本（不是修改意见），将直接整段替换原条款
4. 未命中风险的条款不要输出；宁缺勿滥，不确定的不输出
5. 每个 JSON 对象必须完整闭合；若条款较多，只输出最重要的风险项
6. issue/impact 用简体中文"""
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
1. 输出 Markdown：一级标题为合同名称，条款用"第X条"编号并带条款标题
2. 结构完整：鉴于条款、定义、标的与范围、价款与支付、交付与验收、双方权利义务、违约责任、保密、知识产权、不可抗力、争议解决、其他约定、签署栏
3. 不确定的信息用占位符，如【金额】【日期】
4. 立场均衡但默认保护甲方（采购方）利益
5. 不要使用 Markdown 表格

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

请输出修改后的完整合同。保持原有结构与"第X条"编号体系，只改动需要改动的部分，其余条款原文保留。不要使用 Markdown 表格。

只输出 JSON（不要代码块围栏）：
{{"title": "合同名称", "markdown": "# 合同名称\\n...全文..."}}"""
    return [
        {"role": "system", "content": DRAFT_SYSTEM},
        {"role": "user", "content": user},
    ]
