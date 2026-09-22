"""PDF 解析：pdfplumber 逐页提取文本行"""
from __future__ import annotations

from pathlib import Path

from app.parser.docx_parser import ParagraphInfo


def extract_pdf_lines(path: Path) -> list[ParagraphInfo]:
    """返回 `ParagraphInfo` 列表（保留空行用于结构切分）。

    PDF 没有可靠样式信息，因此 `html` 字段就是按行包裹的 `<p>...</p>` 纯文本 fallback。
    文本量过少时抛错（疑似扫描件，demo 不做 OCR）。
    """
    import html as _html

    import pdfplumber

    paragraphs: list[ParagraphInfo] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                escaped = _html.escape(line).replace("\n", "<br>")
                paragraphs.append(
                    ParagraphInfo(text=line, html=f"<p>{escaped}</p>")
                )
            paragraphs.append(ParagraphInfo(text="", html="<p><br></p>"))  # 页间空行

    total_chars = sum(len(p.text.strip()) for p in paragraphs)
    if total_chars < 50:
        raise ValueError(
            "PDF 可提取文本过少，疑似扫描件（图片型 PDF），"
            "请上传文本型 PDF 或 Word 文档"
        )
    return paragraphs
