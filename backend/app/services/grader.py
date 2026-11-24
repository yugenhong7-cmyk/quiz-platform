"""
判题引擎：
- 单选：对比答案
- 多选：集合完全一致
- 判断：标准化后比较
- 填空：多空、等价表达、人工同义词
- 简答/计算：AI 辅助评分（必须标注"辅助评分"）
"""
import re
from typing import Any, Dict, List, Optional, Tuple

TRUE_SET = {"正确", "对", "是", "true", "t", "y", "√", "1", "yes"}
FALSE_SET = {"错误", "错", "否", "false", "f", "n", "×", "0", "no"}


def normalize_bool(val: Any) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    if val is None:
        return None
    s = str(val).strip().lower()
    s = re.sub(r"\s+", "", s)
    if s in TRUE_SET:
        return True
    if s in FALSE_SET:
        return False
    return None


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", "", s)
    for a, b in [("，", ","), ("。", "."), ("：", ":"), ("；", ";"), ("（", "("), ("）", ")")]:
        s = s.replace(a, b)
    # 去掉末尾标点
    s = s.rstrip(",.;:!，。；：！")
    return s


def grade_objective(qtype: str, user_answer: Any, correct_answer: Any) -> Tuple[bool, str]:
    """客观题判题。返回 (is_correct, note)。"""
    if qtype == "single":
        ua = (str(user_answer).strip().upper() if user_answer is not None else "")
        ca = (str(correct_answer).strip().upper() if correct_answer is not None else "")
        return ua == ca and ua != "", ""

    if qtype == "multiple":
        ua = _to_letter_set(user_answer)
        ca = _to_letter_set(correct_answer)
        if not ua:
            return False, "未作答"
        return ua == ca, ""

    if qtype == "truefalse":
        ub = normalize_bool(user_answer)
        cb = normalize_bool(correct_answer)
        if ub is None:
            return False, "作答格式无法识别"
        return ub == cb, ""

    if qtype == "blank":
        return _grade_blank(user_answer, correct_answer)

    # 简答/计算需要 AI 或人工
    return False, "主观题需 AI 辅助或人工评分"


def _to_letter_set(val: Any) -> set:
    if val is None:
        return set()
    if isinstance(val, (list, tuple, set)):
        return {str(v).strip().upper() for v in val if str(v).strip()}
    s = str(val).strip().upper()
    s = re.sub(r"[\s,，、.．/|\[\]()（）]+", "", s)
    if re.fullmatch(r"[A-H]+", s):
        return set(s)
    # 逗号分隔
    parts = re.split(r"[,，、\s]+", str(val).strip().upper())
    return {p for p in parts if re.fullmatch(r"[A-H]", p)}


def _grade_blank(user_answer: Any, correct_answer: Any) -> Tuple[bool, str]:
    """填空题：支持多空、多个标准答案（等价表达）。"""
    # correct_answer 可能是 ["x"] 或 [["x","等价1"], ["y"]] 或 "x"
    def as_blank_lists(ca):
        if isinstance(ca, str):
            return [[ca]]
        if isinstance(ca, (list, tuple)):
            out = []
            for item in ca:
                if isinstance(item, (list, tuple)):
                    out.append([str(x) for x in item])
                else:
                    # 字符串里可能含 | 分隔等价
                    s = str(item)
                    alts = [a for a in re.split(r"[|｜]", s) if a.strip()]
                    out.append(alts or [s])
            return out
        return [[str(ca)]]

    std = as_blank_lists(correct_answer)
    # 用户答案
    if isinstance(user_answer, (list, tuple)):
        ua = [str(x) for x in user_answer]
    else:
        ua = [x.strip() for x in re.split(r"[;；|｜]", str(user_answer or "")) if x.strip()]

    if not ua or all(not x for x in ua):
        return False, "未作答"

    # 若标准只有一个空，而用户填了一整段，则整体比对
    if len(std) == 1 and len(ua) != 1:
        ua = [" ".join(ua)]

    if len(ua) < len(std):
        return False, f"填空数量不足（应为 {len(std)} 个）"

    all_ok = True
    for i, alts in enumerate(std):
        u = ua[i] if i < len(ua) else ""
        un = normalize_text(u)
        ok = any(normalize_text(a) == un or (a and normalize_text(a) in un) for a in alts)
        if not ok:
            all_ok = False
            break
    return all_ok, ""


def grade_short_answer_rule(user_answer: str, keywords: List[str]) -> Tuple[Optional[bool], str]:
    """
    简答题启发式：命中关键词比例。仅作辅助，返回 None 表示需 AI/人工。
    """
    if not keywords:
        return None, "缺少评分要点，需 AI 或人工评价"
    text = normalize_text(user_answer or "")
    if not text:
        return False, "未作答"
    hit = sum(1 for k in keywords if normalize_text(k) in text)
    ratio = hit / max(len(keywords), 1)
    if ratio >= 0.8:
        return True, f"关键词命中 {hit}/{len(keywords)}（启发式）"
    if ratio <= 0.2:
        return False, f"关键词命中 {hit}/{len(keywords)}（启发式）"
    return None, f"关键词命中 {hit}/{len(keywords)}，建议 AI 复核"


def grade_calculation(user_answer: str, expected: Any, tolerance: float = 1e-6) -> Tuple[Optional[bool], str]:
    """计算题：尝试数值比对（带容差），含单位提取。"""
    if expected is None or expected == "":
        return None, "无标准答案，需人工或 AI 评价"
    ua_nums = _extract_numbers(user_answer)
    ca_nums = _extract_numbers(str(expected))
    if not ua_nums or not ca_nums:
        return None, "无法可靠解析数值，建议 AI 或人工评价"
    try:
        u = ua_nums[-1]
        c = ca_nums[-1]
        if abs(u - c) <= max(tolerance, abs(c) * 1e-6):
            return True, f"数值比对通过（用户 {u} ≈ 标准 {c}）"
        return False, f"数值不一致（用户 {u} vs 标准 {c}）"
    except Exception:
        return None, "数值比对失败，建议 AI 或人工评价"


def _extract_numbers(s: str) -> List[float]:
    if not s:
        return []
    s = str(s).replace(",", "").replace("，", "")
    out = []
    for m in re.finditer(r"-?\d+\.?\d*(?:[eE][+-]?\d+)?", s):
        try:
            out.append(float(m.group(0)))
        except ValueError:
            pass
    return out


def summarize_answer_for_display(qtype: str, answer: Any) -> Any:
    if qtype == "truefalse":
        b = normalize_bool(answer)
        return "正确" if b else ("错误" if b is False else "")
    return answer
