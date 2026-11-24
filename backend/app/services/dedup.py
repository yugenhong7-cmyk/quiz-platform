"""题干规范化、内容哈希与重复检测。"""
import hashlib
import re
from difflib import SequenceMatcher
from typing import List, Optional, Tuple


def normalize_stem(text: str) -> str:
    """题干规范化：去除题号、空白、全角/半角统一、大小写归一。"""
    if not text:
        return ""
    s = text.strip()
    # 去除开头题号：1. 1、 1) （1） 第1题 等
    s = re.sub(r"^\s*(第\s*)?\d+\s*[.、．)）:：]", "", s)
    s = re.sub(r"^[\s]*[（(]\s*\d+\s*[)）]", "", s)
    # 全角数字/字母 → 半角
    s = _fullwidth_to_halfwidth(s)
    # 统一空白
    s = re.sub(r"\s+", "", s)
    # 统一标点
    for a, b in [("，", ","), ("。", "."), ("：", ":"), ("；", ";"), ("？", "?"),
                 ("（", "("), ("）", ")"), ("【", "["), ("】", "]"), ("“", '"'), ("”", '"')]:
        s = s.replace(a, b)
    return s.lower()


def _fullwidth_to_halfwidth(s: str) -> str:
    result = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:
            result.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        else:
            result.append(ch)
    return "".join(result)


def content_hash(stem: str, qtype: str = "") -> str:
    norm = normalize_stem(stem)
    return hashlib.sha256(f"{qtype}|{norm}".encode("utf-8")).hexdigest()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_stem(a), normalize_stem(b)).ratio()


def find_duplicate(
    stem: str,
    qtype: str,
    existing: List[Tuple[int, str, str]],
    threshold: float = 0.92,
) -> Optional[int]:
    """
    existing: [(question_id, stem, qtype)]
    返回重复题目 id，无重复返回 None。
    先精确哈希比对，再做相似度比对。
    """
    h = content_hash(stem, qtype)
    norm = normalize_stem(stem)
    for qid, s, t in existing:
        if t != qtype:
            continue
        if content_hash(s, t) == h:
            return qid
    for qid, s, t in existing:
        if t != qtype:
            continue
        if similarity(stem, s) >= threshold:
            return qid
    return None
