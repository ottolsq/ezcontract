"""contract-copilot.skill 参考文档加载器

Plan A：把本地 skill 中的 markdown 参考注入审查 Prompt。
- 通用参考：review-framework / contract-routing / priority-clauses / clause-library
- 专项参考：根据传入的合同类型，从 references/contract-types/<目录>/<主文件>.md 选择对应主文件

文件读取失败时静默降级（warning 后返回空字符串），保证审查流程不中断。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import settings


def _safe_read(path: Path) -> str:
    """读取 markdown；缺失/异常时返回空字符串"""
    try:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


@lru_cache(maxsize=4)
def _cached_text(path_str: str) -> str:
    """lru_cache 不支持 Path，按字符串缓存；改文件后进程重启即生效"""
    return _safe_read(Path(path_str))


def load_skill_reference(path: Path) -> str:
    """读取 skill 中的单个 markdown 参考文档（带缓存）"""
    if path is None:
        return ""
    return _cached_text(str(path))


# 12 类合同目录编号 -> (默认主文件名, 别名集合)
# 与 references/contract-routing.md / priority-clauses.md 保持一致
_TYPE_INDEX: dict[str, tuple[str, tuple[str, ...]]] = {
    "01-sale": ("movables-sale.md", ("sale", "buy", "purchase", "goods", "买卖")),
    "02-lease": ("commercial-housing.md", ("lease", "rent", "rental", "租赁")),
    "03-service": ("general-service.md", ("service", "服务", "outsource", "consult")),
    "05-guarantee": ("general-guarantee.md", ("guarantee", "surety", "担保")),
    "06-lending-gift": ("general-lending.md", ("loan", "lend", "borrow", "借贷", "gift", "赠与")),
    "07-internet": ("user-agreement.md", ("internet", "online", "saas", "platform", "互联网", "网站", "app")),
    "09-employment": ("general-employment.md", ("employment", "labor", "劳动合同", "用工")),
    "10-real-estate": ("commercial-housing.md", ("real-estate", "property", "房地产")),
    "11-construction": ("general-construction.md", ("construction", "build", "工程", "施工")),
    "12-corporate-investment": ("general-investment.md", ("investment", "equity", "股权", "投资")),
}


def _resolve_type_dir(contract_type: str | None) -> Path | None:
    """根据合同类型关键字匹配 contract-types/ 下子目录"""
    if not contract_type:
        return None
    key = contract_type.strip().lower()
    if not key:
        return None
    for dir_name, (default_file, aliases) in _TYPE_INDEX.items():
        if key == dir_name or key in aliases or contract_type == dir_name:
            type_dir = settings.CONTRACT_TYPES_DIR / dir_name
            if type_dir.exists():
                # 优先使用默认主文件，缺失时回落到目录下第一个 .md
                default_path = type_dir / default_file
                if default_path.exists():
                    return default_path
                # 回落
                for sub in sorted(type_dir.glob("*.md")):
                    return sub
    return None


@lru_cache(maxsize=8)
def _cached_type_ref(contract_type: str | None) -> str:
    type_dir = _resolve_type_dir(contract_type)
    if type_dir is None:
        return ""
    return _safe_read(type_dir)


def get_skill_references(contract_type: str | None = None) -> dict[str, str]:
    """返回审查 Prompt 所需的全部 skill 参考

    返回字段：
    - review_framework: 三层审查 + 四步流程 + 通用风险清单
    - contract_routing: 12 类合同路由
    - priority_clauses: 12 类合同优先审查顺序
    - clause_library: 推荐条款措辞库
    - contract_type_ref: 专项合同类型参考（可选）
    """
    return {
        "review_framework": load_skill_reference(settings.REVIEW_FRAMEWORK_PATH),
        "contract_routing": load_skill_reference(settings.CONTRACT_ROUTING_PATH),
        "priority_clauses": load_skill_reference(settings.PRIORITY_CLAUSES_PATH),
        "clause_library": load_skill_reference(settings.CLAUSE_LIBRARY_PATH),
        "contract_type_ref": _cached_type_ref(contract_type),
    }