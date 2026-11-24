"""文件导入解析：TXT / CSV / Excel / Word / PDF。扫描版 PDF 提供 OCR 扩展点。"""
import csv
import io
import os
from typing import Any, Dict, List, Optional, Tuple


def extract_text_from_file(filename: str, content: bytes) -> Tuple[str, Optional[str]]:
    """
    返回 (纯文本, 错误信息)。错误为 None 表示成功。
    """
    ext = os.path.splitext(filename or "")[1].lower()
    try:
        if ext in (".txt", ".md", ".text", ""):
            return _decode_text(content), None
        if ext == ".csv":
            return _from_csv(content), None
        if ext in (".xlsx", ".xlsm"):
            return _from_xlsx(content), None
        if ext == ".xls":
            return "", "暂不支持 .xls 旧格式，请另存为 .xlsx 或 .csv"
        if ext in (".docx", ".doc"):
            return _from_docx(content), None
        if ext == ".pdf":
            return _from_pdf(content)
        # 未知扩展名按文本尝试
        return _decode_text(content), None
    except Exception as e:
        return "", f"文件解析失败：{type(e).__name__}: {e}"


def _decode_text(content: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _from_csv(content: bytes) -> str:
    text = _decode_text(content)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return ""
    # 识别表头列
    header = [h.strip().lower() for h in rows[0]]
    has_header = any(k in header for k in ["题干", "题目", "stem", "question", "题型", "答案"])

    def row_to_block(cells: List[str]) -> str:
        if has_header:
            mapping = {}
            for i, h in enumerate(header):
                if i < len(cells):
                    mapping[h] = cells[i].strip()
            stem = mapping.get("题干") or mapping.get("题目") or mapping.get("stem") or mapping.get("question") or ""
            qtype = mapping.get("题型") or mapping.get("type") or ""
            answer = mapping.get("答案") or mapping.get("answer") or ""
            analysis = mapping.get("解析") or mapping.get("explanation") or ""
            opts = []
            for key, label in [("a", "A"), ("option_a", "A"), ("选项a", "A"), ("选项1", "A"),
                               ("b", "B"), ("option_b", "B"), ("选项b", "B"), ("选项2", "B"),
                               ("c", "C"), ("option_c", "C"), ("选项c", "C"), ("选项3", "C"),
                               ("d", "D"), ("option_d", "D"), ("选项d", "D"), ("选项4", "D")]:
                if key in mapping and mapping[key]:
                    opts.append(f"{label}. {mapping[key]}")
            parts = [f"1. {stem}"]
            if qtype:
                parts.append(f"【{qtype}】")
            parts.extend(opts)
            if answer:
                parts.append(f"答案：{answer}")
            if analysis:
                parts.append(f"解析：{analysis}")
            return "\n".join(p for p in parts if p)
        # 无表头：按列拼接
        return " ".join(c for c in cells if c.strip())

    blocks = [row_to_block(r) for r in rows[1:] if any(c.strip() for c in r)] if has_header else \
             [row_to_block(r) for r in rows if any(c.strip() for c in r)]
    return "\n\n".join(blocks)


def _from_xlsx(content: bytes) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    blocks: List[str] = []
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        try:
            first = next(rows)
        except StopIteration:
            continue
        header = [str(c).strip().lower() if c is not None else "" for c in first]
        has_header = any(k in header for k in ["题干", "题目", "stem", "question", "题型", "答案"])

        def row_to_block(cells) -> str:
            vals = ["" if c is None else str(c).strip() for c in cells]
            if has_header:
                mapping = {header[i]: vals[i] for i in range(min(len(header), len(vals)))}
                stem = mapping.get("题干") or mapping.get("题目") or mapping.get("stem") or mapping.get("question") or ""
                qtype = mapping.get("题型") or mapping.get("type") or ""
                answer = mapping.get("答案") or mapping.get("answer") or ""
                analysis = mapping.get("解析") or mapping.get("explanation") or ""
                opts = []
                for key, label in [("a", "A"), ("option_a", "A"), ("选项a", "A"), ("选项1", "A"),
                                   ("b", "B"), ("option_b", "B"), ("选项b", "B"), ("选项2", "B"),
                                   ("c", "C"), ("option_c", "C"), ("选项c", "C"), ("选项3", "C"),
                                   ("d", "D"), ("option_d", "D"), ("选项d", "D"), ("选项4", "D")]:
                    if mapping.get(key):
                        opts.append(f"{label}. {mapping[key]}")
                parts = [f"1. {stem}"]
                if qtype:
                    parts.append(f"【{qtype}】")
                parts.extend(opts)
                if answer:
                    parts.append(f"答案：{answer}")
                if analysis:
                    parts.append(f"解析：{analysis}")
                return "\n".join(p for p in parts if p)
            return " ".join(v for v in vals if v)

        data_rows = list(rows)
        for r in data_rows:
            if any(c is not None and str(c).strip() for c in r):
                blocks.append(row_to_block(r))
    return "\n\n".join(blocks)


def _from_docx(content: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    # 表格
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" ".join(cells))
    return "\n".join(parts)


def _from_pdf(content: bytes) -> Tuple[str, Optional[str]]:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=content, filetype="pdf")
    texts = []
    for page in doc:
        t = page.get_text("text")
        texts.append(t or "")
    full = "\n".join(texts)
    stripped = full.strip()
    # 扫描版检测：几乎无文本层
    if len(stripped) < 20:
        doc.close()
        return "", (
            "该 PDF 几乎没有文本层，疑似扫描版。"
            "当前版本不内置 OCR，请先用 OCR 工具转为文本/Word 后导入；"
            "或在 services/ocr.py 扩展 OCR 模块（如 PaddleOCR / Tesseract）。"
        )
    doc.close()
    return full, None


# OCR 扩展点（可选）
def ocr_available() -> bool:
    """是否已接入 OCR 引擎。当前未接入。"""
    return False
