"""当日弹框语音录入 default_date 兜底测试

运行：./venv/bin/python -m unittest tests.test_itinerary_default_date -v
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.schemas.itinerary import ItineraryParseOut, ItineraryEventLLM, VoiceParseIn  # noqa: E402
from app.services import itinerary_service as svc  # noqa: E402
from app.services.compliance_db import init_db  # noqa: E402


def _llm_out(**ev_kw):
    """构造一条行程的 LLM 输出；默认缺日期"""
    ev = ItineraryEventLLM(title="品牌发布会", **ev_kw)
    return ItineraryParseOut(events=[ev])


class DefaultDateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "compliance.db"
        init_db(self.db_path)
        self._orig = svc.settings.COMPLIANCE_DB_PATH
        svc.settings.COMPLIANCE_DB_PATH = self.db_path

    def tearDown(self):
        svc.settings.COMPLIANCE_DB_PATH = self._orig
        self._tmp.cleanup()

    def _parse(self, body):
        return asyncio.run(svc.parse_voice(body))

    def test_default_date_backfills_empty(self):
        """语音没提日期 → event_date 兜底为 default_date；有人员时 needs_review=False"""
        # 先建一个人员，让 _resolve_artist 能解析到 artist_id
        with patch.object(svc, "chat_json", new=AsyncMock(return_value=_llm_out())):
            out = self._parse(
                VoiceParseIn(
                    text="三点拍摄",
                    default_date="2026-10-20",
                    default_artist_id=svc.create_artist(
                        svc.ArtistCreateIn(name="小王")
                    )["id"],
                )
            )
        self.assertEqual(out["events"][0]["event_date"], "2026-10-20")
        self.assertFalse(out["events"][0]["needs_review"])

    def test_default_date_filled_by_voice(self):
        """语音提到日期 → 语音日期优先，default_date 不覆盖"""
        with patch.object(
            svc, "chat_json",
            new=AsyncMock(return_value=_llm_out(event_date="2026-11-01")),
        ):
            out = self._parse(VoiceParseIn(text="11月1号三点拍摄", default_date="2026-10-20"))
        self.assertEqual(out["events"][0]["event_date"], "2026-11-01")

    def test_default_date_invalid_ignored(self):
        """default_date 非法（非 YYYY-MM-DD）→ 忽略兜底，不 500"""
        with patch.object(svc, "chat_json", new=AsyncMock(return_value=_llm_out())):
            out = self._parse(VoiceParseIn(text="三点拍摄", default_date="不是日期"))
        self.assertEqual(out["events"][0]["event_date"], "")
        self.assertTrue(out["events"][0]["needs_review"])

    def test_parse_voice_audio_passes_default_date(self):
        """parse-voice-audio 链路把 default_date 透传给 parse_voice"""
        captured = {}

        async def fake_parse(body):
            captured["default_date"] = body.default_date
            return {"events": []}

        with (
            patch.object(svc, "transcribe", new=AsyncMock(return_value="明天拍摄")),
            patch.object(svc, "parse_voice", new=fake_parse),
        ):
            asyncio.run(
                svc.parse_voice_audio(b"f", "audio/webm", None, None, "2026-10-20")
            )
        self.assertEqual(captured["default_date"], "2026-10-20")


if __name__ == "__main__":
    unittest.main()
