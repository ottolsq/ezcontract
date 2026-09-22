"""应用配置：读取 .env，集中管理"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录 = app/ 的上一级
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


class Settings:
    """全局配置（demo 从简，不用 pydantic-settings）"""

    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "").rstrip("/")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-flash")

    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    EXPORT_DIR: Path = DATA_DIR / "exports"

    RULES_PATH: Path = BASE_DIR / "rules" / "erp_rules.md"

    # 审查分批参数
    BATCH_MAX_CLAUSES: int = 8
    BATCH_MAX_CHARS: int = 2500

    # LLM 参数
    REVIEW_TEMPERATURE: float = 0.0
    DRAFT_TEMPERATURE: float = 0.3
    # 网关模型带 reasoning（思维链占用 token），max_tokens 需给足
    REVIEW_MAX_TOKENS: int = 12000
    DRAFT_MAX_TOKENS: int = 16000

    # 风险分确定性权重
    SCORE_HIGH_WEIGHT: int = 15
    SCORE_MEDIUM_WEIGHT: int = 7

    # 演示账号（Demo 定位：单账号，不做用户表/哈希；改密码改 .env 即可）
    DEMO_USERNAME: str = os.getenv("DEMO_USERNAME", "admin")
    DEMO_PASSWORD: str = os.getenv("DEMO_PASSWORD", "faheng2024")
    # 演示 token 有效期（秒）—— 进程内存白名单，重启后失效需重新登录
    AUTH_TOKEN_TTL: int = int(os.getenv("AUTH_TOKEN_TTL", "86400"))

    def ensure_dirs(self) -> None:
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.EXPORT_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
