"""
题目解析引擎（第一层规则识别）。

负责：
1. 将大段原始文本拆分为单个题目
2. 识别题型（单选/多选/判断/填空/简答/计算/未识别）
3. 提取题干、选项、答案、解析、难度、知识点
4. 输出统一结构与置信度
"""
import re
from typing import Any, Dict, List, Optional, Tuple

# ---------- 拆题 ----------
# 题目起始：1. 1、 1) （1） 第1题 一、 等
_Q_START = re.compile(
    r"(?m)^\s*(?:"
    r"(?:第\s*)?(\d{1,4})\s*[.、．)）:：]\s*"          # 1. 1、 1) 1:
    r"|[（(]\s*(\d{1,4})\s*[)）]\s*"                    # (1) （1）
    r")(?=\S)"
)
_SECTION = re.compile(r"^\s*[一二三四五六七八九十]+\s*[、.．]\s*\S")

# 选项行：A. A、 A) （A） 1. (选项用数字时)
_OPT_LINE = re.compile(
    r"(?m)^\s*([A-Ha-h])\s*[.、．)）:：]\s*(.+?)\s*$"
)
_OPT_LINE_PAREN = re.compile(
    r"(?m)^\s*[（(]\s*([A-Ha-h])\s*[)）]\s*[.、．:：]?\s*(.+?)\s*$"
)
_OPT_NUM_LINE = re.compile(
    r"(?m)^\s*([1-8])\s*[.、．)）:：]\s*(.+?)\s*$"
)

# 答案行（支持 答案： / 答案B / 【答案】B 等形态；行前可带题号）
_ANS_LINE = re.compile(
    r"(?m)^\s*(?:(?:第\s*)?\d{1,4}\s*[.、．)）:：]\s*)?"
    r"(?:[【\[［（(]\s*(?:标准答案|正确答案|参考答案|答案|答)\s*[】\]］）)]\s*[::：]?\s*"
    r"|(?:标准答案|正确答案|参考答案|答案|答)\s*(?:[::：]\s*|\s+|(?=[A-Ha-h]))"
    r")(.+?)\s*$"
)
_ANS_INLINE = re.compile(
    r"(?:[【\[［（(]\s*(?:标准答案|正确答案|参考答案|答案)\s*[】\]］）)]|(?:标准答案|正确答案|参考答案|答案)\s*[::：])\s*"
    r"([A-Ha-h](?:\s*[、,，.．/|\-]?\s*[A-Ha-h]){0,7}|正确|错误|对|错|是|否|true|false|True|False|√|×)"
)

# 解析行（支持 解析： / 【解析】xxx 等形态；行前可带题号）
_EXP_LINE = re.compile(
    r"(?m)^\s*(?:(?:第\s*)?\d{1,4}\s*[.、．)）:：]\s*)?"
    r"(?:[【\[［（(]\s*(?:答案解析|试题解析|参考解析|解析|解题思路|分析)\s*[】\]］）)]\s*[::：]?\s*"
    r"|(?:答案解析|试题解析|参考解析|解题思路|解析|分析)\s*[::：]\s*"
    r")(.*)$"
)

# 括号标记：【答案】B → 答案：B（处理与选项/答案粘连在同一行的情况）
_MARKER_TAG = re.compile(
    r"[【\[［（(]\s*(标准答案|正确答案|参考答案|答案解析|试题解析|参考解析|解题思路|知识点|考点|答案|解析|难度|分析)\s*[】\]］）)]\s*[::：]?\s*"
)
# 行内粘连的冒号标记：…答案：B 解析：xxx → 拆成独立行。
# 长词优先匹配（参考答案/答案解析），避免在"参考答案"内部误拆"答案"。
# 短词（答/解析/分析等）加前后文守卫，防止把"数据解析："这类内容误拆。
_INLINE_MARK = re.compile(
    r"((?:标准答案|正确答案|参考答案|答案解析|试题解析|参考解析|解题思路|答案)\s*[::：]"
    r"|(?<![A-Za-z0-9\u4e00-\u9fff])(?:答|解析|分析|难度|知识点|考点)\s*[::：])"
)

# 难度
_DIFF_LINE = re.compile(r"(?m)^\s*难度\s*[::：]\s*([容易简单中等困难1-3])")

# 知识点
_KP_LINE = re.compile(r"(?m)^\s*(?:知识点|考点|知识考点)\s*[::：]\s*(.+?)\s*$")

# 归一化时，标记行的"值"若独占下一行，可并入；下列行首形态不能被并入
_MERGE_BLOCK = re.compile(
    r"^\s*(?:"
    r"[A-Ha-h]\s*[.、．)）:：]"                       # 选项行 A. A、
    r"|[（(]\s*[A-Ha-h]\s*[)）]"                      # （A）选项
    r"|[【\[［（(]\s*(?:标准答案|正确答案|参考答案|答案解析|试题解析|参考解析|解题思路|答案|解析|难度|知识点|考点|分析)"
    r"|(?:标准答案|正确答案|参考答案|答案解析|试题解析|参考解析|解题思路|答案|解析|难度|知识点|考点|分析)\s*[::：]"
    r"|(?:第\s*)?\d{1,4}\s*[.、．)）:：]"             # 新题号
    r")"
)

# 解析续行的终止标记
_TAIL_MARK = re.compile(
    r"^\s*(?:难度|知识点|考点|知识考点|标准答案|正确答案|参考答案|答案)\s*[::：]"
)

# 填空标记
_BLANK_MARK = re.compile(r"_{2,}|（\s*）|\(\s*\)|\{\s*\}|\[\s*\]")

# 判断题关键词
_TRUEFALSE_KW = re.compile(r"(判断|正确|错误|对错|是非|√|×|true|false)", re.I)

QTYPE_LABEL = {
    "single": "单选题", "multiple": "多选题", "truefalse": "判断题",
    "blank": "填空题", "shortanswer": "简答题", "calculation": "计算题",
    "unknown": "未识别题型",
}


def _normalize_markers(text: str) -> str:
    """把与选项/题干粘连在同一行的【答案】【解析】等标记拆到独立行。

    例：D. 选项内容【答案】B【解析】xxx  →  D. 选项内容\\n答案：B\\n解析：xxx
    """
    # 1) 括号标记【答案】→ 行标记 答案：
    text = _MARKER_TAG.sub(lambda m: "\n" + m.group(1) + "：", text)
    # 2) 行内冒号标记拆行（如 …答案：B 解析：xxx）
    out_lines = []
    for line in text.split("\n"):
        parts = _INLINE_MARK.split(line)
        # split 含捕获组：[前段, 标记1, 中段, 标记2, 后段…]
        if len(parts) == 1:
            out_lines.append(line)
            continue
        buf = parts[0].strip()
        if buf:
            out_lines.append(buf)
        for i in range(1, len(parts), 2):
            mark = parts[i]
            seg = parts[i + 1] if i + 1 < len(parts) else ""
            out_lines.append((mark + seg).strip())
    return "\n".join(out_lines)


def split_questions(raw_text: str) -> List[str]:
    """把大段文本按题号拆分为题目块。"""
    if not raw_text or not raw_text.strip():
        return []
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_Q_START.finditer(text))
    if not matches:
        # 没有题号，尝试按空行/分隔线拆
        blocks = re.split(r"\n\s*\n\s*\n+|\n-{3,}\n", text)
        return [b.strip() for b in blocks if b.strip()]
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def _extract_options(block: str) -> Tuple[List[Dict[str, str]], str, str]:
    """返回 (options, 剩余题干文本, 选项区域原文)。"""
    lines = block.split("\n")
    opt_start = -1
    options: List[Dict[str, str]] = []
    used_pat = None

    for idx, line in enumerate(lines):
        m = _OPT_LINE.match(line) or _OPT_LINE_PAREN.match(line)
        if m:
            if opt_start == -1:
                opt_start = idx
                # 判断是否数字选项（题干里含 ①② 或选项是 1. 2.）
                used_pat = "letter"
            if used_pat == "letter":
                options.append({"label": m.group(1).upper(), "content": m.group(2).strip()})
                continue
        m2 = _OPT_NUM_LINE.match(line)
        if m2 and opt_start == -1 and not _Q_START.match(line):
            # 数字选项：仅当行内不像题号（题号匹配会在 split 时已切掉）
            opt_start = idx
            used_pat = "num"
            options.append({"label": m2.group(1), "content": m2.group(2).strip()})
            continue
        if opt_start != -1:
            # 选项区域内续行合并到上一个选项
            if options and line.strip() and not _ANS_LINE.match(line) and not _EXP_LINE.match(line):
                if used_pat == "letter" and not _OPT_LINE.match(line) and not _OPT_LINE_PAREN.match(line):
                    options[-1]["content"] += " " + line.strip()
                    continue
                if used_pat == "num" and not _OPT_NUM_LINE.match(line):
                    options[-1]["content"] += " " + line.strip()
                    continue

    if opt_start == -1:
        return [], block, ""

    stem_part = "\n".join(lines[:opt_start]).strip()
    rest_part = "\n".join(lines[opt_start:]).strip()
    return options, stem_part, rest_part


def _clean_stem(stem: str) -> str:
    # 去题号
    stem = re.sub(r"^\s*(?:第\s*)?\d+\s*[.、．)）:：]\s*", "", stem)
    stem = re.sub(r"^\s*[（(]\s*\d+\s*[)）]\s*", "", stem)
    # 去题型标注：【单选题】 (多选) 等（必须带括号或冒号，避免误伤"计算机"等词）
    stem = re.sub(r"^\s*[【\[（(]\s*(单选题?|多选题?|判断题?|填空题?|简答题?|计算题?|选择题)\s*[】\]）)]\s*", "", stem)
    stem = re.sub(r"^\s*(单选题?|多选题?|判断题?|填空题?|简答题?|计算题?)\s*[::：]\s*", "", stem)
    return stem.strip()


def _detect_type(stem: str, options: List[Dict], answer_raw: str) -> Tuple[str, float, List[str]]:
    """
    题型识别。返回 (qtype, confidence, uncertain_fields)。
    注意：有 4 个选项不等于单选题——必须结合答案格式判断。
    """
    uncertain: List[str] = []
    ans = (answer_raw or "").strip()
    ans_clean = re.sub(r"\s+", "", ans).upper()

    # 判断题：无选项 + 答案为对错类
    tf_answers = {"正确", "错误", "对", "错", "是", "否", "TRUE", "FALSE", "√", "×", "T", "F", "Y", "N"}
    if not options:
        if ans_clean in tf_answers or _TRUEFALSE_KW.search(stem):
            return "truefalse", 0.9, uncertain
        if _BLANK_MARK.search(stem) or re.search(r"填空", stem):
            return "blank", 0.85, uncertain
        # 计算题特征
        if re.search(r"(计算|求解|求出|列出算式|写出计算|结果为)", stem) or re.search(r"=\s*\?", stem):
            return "calculation", 0.75, uncertain
        # 简答题
        if re.search(r"(简述|简答|说明|解释|为什么|论述|分析|比较|区别|写出|列举)", stem) and len(stem) > 15:
            return "shortanswer", 0.75, uncertain
        if ans and len(ans) > 20:
            return "shortanswer", 0.7, uncertain
        if not ans:
            uncertain.append("answer")
            return "unknown", 0.3, uncertain
        return "shortanswer", 0.5, uncertain

    # 有选项：单选 vs 多选
    # 答案格式解析
    letters = _parse_answer_letters(ans)
    if letters:
        if len(letters) > 1:
            return "multiple", 0.95, uncertain
        # 单个字母答案：若题干/答案行明确写了"多选"仍按多选
        if re.search(r"多选", stem) or re.search(r"多选", ans):
            uncertain.append("qtype")
            return "multiple", 0.6, uncertain
        return "single", 0.95, uncertain

    # 答案是数字/文本（可能是填空伪装成选择）
    if ans and not letters:
        uncertain.append("answer")
        # 答案疑似对应选项内容
        for opt in options:
            if ans_clean and ans_clean in re.sub(r"\s+", "", opt["content"]).upper():
                return "single", 0.6, uncertain
        return "unknown", 0.35, uncertain

    # 无答案：根据题干提示
    if re.search(r"多选|下列.*(?:都|均|哪些)", stem):
        uncertain.append("answer")
        return "multiple", 0.55, uncertain
    uncertain.append("answer")
    return "single", 0.5, uncertain


def _parse_answer_letters(ans: str) -> List[str]:
    """解析多种答案格式：ABC / A,B,C / A、B、C / A B C / (A) / 答案：AB"""
    if not ans:
        return []
    s = ans.strip()
    # 去掉"答案："前缀残留
    s = re.sub(r"^\s*(答案|正确答案|标准答案|参考答案|答)\s*[::：]?\s*", "", s)
    # 去掉括号
    s = s.replace("(", "").replace(")", "").replace("（", "").replace("）", "")
    s = s.replace("[", "").replace("]", "")
    # 统一分隔符为逗号
    s = re.sub(r"[、,，.．/|\s\-—]+", ",", s).strip(",")
    parts = [p for p in s.split(",") if p]
    letters = []
    for p in parts:
        p = p.upper()
        if re.fullmatch(r"[A-H]", p):
            letters.append(p)
        elif re.fullmatch(r"[A-H]{2,8}", p):
            letters.extend(list(p))
        else:
            return []
    return letters


def _parse_truefalse_answer(ans: str) -> Optional[bool]:
    s = re.sub(r"\s+", "", (ans or "")).lower()
    true_set = {"正确", "对", "是", "true", "t", "y", "√", "1"}
    false_set = {"错误", "错", "否", "false", "f", "n", "×", "0"}
    if s in true_set:
        return True
    if s in false_set:
        return False
    return None


def parse_question_block(block: str, index: int = 0) -> Dict[str, Any]:
    """解析单个题目块。"""
    result: Dict[str, Any] = {
        "index": index,
        "raw_text": block,
        "qtype": "unknown",
        "stem": "",
        "options": [],
        "answer": "",
        "explanation": "",
        "difficulty": 2,
        "knowledge_points": [],
        "confidence": 0.0,
        "uncertain_fields": [],
        "status": "ok",
        "error": "",
    }
    if not block or not block.strip():
        result["status"] = "failed"
        result["error"] = "空题目"
        return result

    # 归一化：把粘连在选项/题干行内的【答案】【解析】等标记拆到独立行
    working = _normalize_markers(block)
    # 提取答案行
    answer_raw = ""
    ans_m = list(_ANS_LINE.finditer(working))
    if ans_m:
        answer_raw = ans_m[-1].group(1).strip()
        # 移除答案行（保留解析行等）
        working = _ANS_LINE.sub("", working)
    else:
        inline = _ANS_INLINE.search(working)
        if inline:
            answer_raw = inline.group(1).strip()
            working = working[:inline.start()] + working[inline.end():]

    # 提取解析
    explanation = ""
    exp_m = list(_EXP_LINE.finditer(working))
    if exp_m:
        explanation = exp_m[-1].group(1).strip()
        # 解析可能跨行：取到下一个标记或结尾
        tail_start = exp_m[-1].end()
        tail = working[tail_start:]
        extra_lines = []
        for ln in tail.split("\n"):
            if re.match(r"^\s*(难度|知识点|考点|答案|正确答案|标准答案)\s*[::：]", ln):
                break
            if ln.strip():
                extra_lines.append(ln.strip())
        if extra_lines:
            explanation = (explanation + " " + " ".join(extra_lines)).strip()
        working = _EXP_LINE.sub("", working)

    # 提取难度
    diff_m = _DIFF_LINE.search(working)
    if diff_m:
        d = diff_m.group(1)
        result["difficulty"] = {"1": 1, "2": 2, "3": 3, "容易": 1, "简单": 1, "中等": 2, "困难": 3}.get(d, 2)
        working = _DIFF_LINE.sub("", working)

    # 提取知识点
    kp_m = _KP_LINE.search(working)
    if kp_m:
        kps = re.split(r"[、,，;；/|]", kp_m.group(1))
        result["knowledge_points"] = [k.strip() for k in kps if k.strip()]
        working = _KP_LINE.sub("", working)

    # 提取选项
    options, stem_part, _opt_rest = _extract_options(working)

    # 若选项区域里残留答案/解析（行式），已在上面处理过 working，但 options 来自 working
    # 进一步从 stem_part 清理
    stem = _clean_stem(stem_part) if stem_part else _clean_stem(working)
    if not stem:
        # 兜底：用第一行
        first = next((ln for ln in block.split("\n") if ln.strip()), "")
        stem = _clean_stem(first)
        if not stem:
            result["status"] = "failed"
            result["error"] = "无法提取题干"
            return result

    result["stem"] = stem
    result["options"] = [{"label": o["label"], "content": o["content"], "is_correct": False} for o in options]
    result["explanation"] = explanation

    # 题型识别
    qtype, confidence, uncertain = _detect_type(stem, options, answer_raw)
    result["qtype"] = qtype
    result["confidence"] = confidence

    # 标准化答案
    if qtype == "single":
        letters = _parse_answer_letters(answer_raw)
        if letters:
            result["answer"] = letters[0]
        else:
            result["answer"] = ""
            uncertain.append("answer")
            confidence = min(confidence, 0.5)
    elif qtype == "multiple":
        letters = _parse_answer_letters(answer_raw)
        result["answer"] = letters
        if not letters:
            uncertain.append("answer")
            confidence = min(confidence, 0.4)
    elif qtype == "truefalse":
        tb = _parse_truefalse_answer(answer_raw)
        result["answer"] = tb if tb is not None else ""
        if tb is None:
            uncertain.append("answer")
            confidence = min(confidence, 0.4)
    elif qtype == "blank":
        # 填空答案：按分号/竖线/多个下划线拆
        ans = re.sub(r"^\s*(答案|正确答案|标准答案)\s*[::：]\s*", "", answer_raw or "")
        blanks = re.split(r"[;；|｜]|\s{2,}", ans)
        blanks = [b.strip() for b in blanks if b.strip()]
        if blanks:
            result["answer"] = blanks
        else:
            result["answer"] = []
            uncertain.append("answer")
            confidence = min(confidence, 0.4)
    else:
        result["answer"] = answer_raw.strip() if answer_raw else ""
        if not result["answer"]:
            uncertain.append("answer")

    # 校验：选择题答案与选项匹配
    if qtype in ("single", "multiple"):
        opt_labels = {o["label"].upper() for o in result["options"]}
        ans_val = result["answer"]
        ans_letters = [ans_val] if isinstance(ans_val, str) else (ans_val or [])
        bad = [a for a in ans_letters if a and a.upper() not in opt_labels]
        if bad:
            uncertain.append("answer_mismatch")
            confidence = min(confidence, 0.45)
        if not result["options"]:
            uncertain.append("options")
            confidence = min(confidence, 0.4)

    result["confidence"] = round(confidence, 3)
    result["uncertain_fields"] = uncertain

    # 状态判定
    if not result["stem"]:
        result["status"] = "failed"
        result["error"] = "题干缺失"
    elif qtype == "unknown":
        result["status"] = "need_review"
    elif "answer" in uncertain or "answer_mismatch" in uncertain:
        result["status"] = "need_review"
        if not result["answer"]:
            result["status"] = "need_review"
    elif confidence < 0.6:
        result["status"] = "need_review"

    return result


def parse_raw_text(raw_text: str) -> List[Dict[str, Any]]:
    """解析整段原始文本 → 结构化题目列表。"""
    blocks = split_questions(raw_text)
    results = []
    for i, block in enumerate(blocks, 1):
        results.append(parse_question_block(block, index=i))
    return results


# ---------- 便捷：结构化 → 模型字段 ----------
def question_answer_payload(q: Dict[str, Any]) -> Any:
    return q.get("answer", "")


def validate_parsed(q: Dict[str, Any]) -> Tuple[bool, str]:
    """写库前校验。"""
    if not q.get("stem"):
        return False, "题干为空"
    qtype = q.get("qtype", "unknown")
    if qtype == "unknown":
        return False, "题型未识别"
    if qtype in ("single", "multiple"):
        opts = q.get("options") or []
        if len(opts) < 2:
            return False, "选项不足 2 个"
        ans = q.get("answer")
        letters = [ans] if isinstance(ans, str) else (ans or [])
        letters = [a for a in letters if a]
        if not letters:
            return False, "缺少答案"
        labels = {o["label"].upper() for o in opts}
        for a in letters:
            if a.upper() not in labels:
                return False, f"答案 {a} 与选项不匹配"
    if qtype == "truefalse":
        if q.get("answer") not in (True, False):
            return False, "判断题答案无效"
    return True, ""
