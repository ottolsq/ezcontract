"""PDF 解析：pdfplumber 逐页提取文本行"""
from __future__ import annotations

from pathlib import Path


def extract_pdf_lines(path: Path) -> list[str]:
    """返回文本行列表（保留空行用于结构切分）。

    文本量过少时抛错（疑似扫描件，demo 不做 OCR）。
    """
    import pdfplumber

    lines: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(text.splitlines())
            lines.append("")  # 页间空行

    total_chars = sum(len(l.strip()) for l in lines)
    if total_chars < 50:
        raise ValueError(
            "PDF 可提取文本过少，疑似扫描件（图片型 PDF），"
            "请上传文本型 PDF 或 Word 文档"
        )
    return lines
