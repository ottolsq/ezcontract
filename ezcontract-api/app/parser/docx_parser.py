"""DOCX 解析：python-docx 段落提取（表格文本跳过，导出时原样保留）"""
from __future__ import annotations

from pathlib import Path


def extract_docx_paragraphs(path: Path) -> list[str]:
    """返回 body 级段落文本列表（含空行，下标即导出回填锚点）"""
    from docx import Document

    doc = Document(str(path))
    return [p.text for p in doc.paragraphs]
