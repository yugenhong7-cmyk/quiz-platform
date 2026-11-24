"""单元测试：题目拆分、题型识别、答案校验、重复检测、判题引擎。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.parser import (
    split_questions, parse_question_block, parse_raw_text, validate_parsed,
)
from app.services.grader import grade_objective, normalize_bool
from app.services.dedup import content_hash, similarity, find_duplicate, normalize_stem


class TestSplit:
    def test_split_by_number(self):
        raw = "1. 第一题？\nA. a\n答案：A\n\n2. 第二题？\nA. x\n答案：A\n\n3. 第三题\n答案：正确"
        blocks = split_questions(raw)
        assert len(blocks) == 3

    def test_split_paren_number(self):
        raw = "（1）题目一？\nA. 1\n答案：A\n（2）题目二？\nA. 1\n答案：A"
        blocks = split_questions(raw)
        assert len(blocks) == 2

    def test_no_number_split_by_blank(self):
        raw = "题目甲？\n答案：A\n\n\n题目乙？\n答案：B"
        blocks = split_questions(raw)
        assert len(blocks) == 2


class TestTypeDetect:
    def test_single_choice(self):
        q = parse_question_block("1. CPU 负责什么？\nA. 存储\nB. 执行指令\nC. 显示\nD. 联网\n答案：B")
        assert q["qtype"] == "single"
        assert q["answer"] == "B"
        assert len(q["options"]) == 4

    def test_multiple_choice_formats(self):
        for ans in ["ABD", "A,B,D", "A、B、D", "A B D", "A,B，D"]:
            q = parse_question_block(f"1. 多选题测试？\nA. 一\nB. 二\nC. 三\nD. 四\n答案：{ans}")
            assert q["qtype"] == "multiple", ans
            assert sorted(q["answer"]) == ["A", "B", "D"], (ans, q["answer"])

    def test_not_single_just_because_four_options(self):
        """有 4 个选项但答案是多选格式时不能判为单选。"""
        q = parse_question_block("1. 测试？\nA. a\nB. b\nC. c\nD. d\n答案：AC")
        assert q["qtype"] == "multiple"

    def test_truefalse(self):
        q = parse_question_block("1. FIFO 是先进先出算法。\n答案：正确")
        assert q["qtype"] == "truefalse"
        assert q["answer"] is True
        q2 = parse_question_block("2. 地球是方的。\n答案：错误")
        assert q2["qtype"] == "truefalse"
        assert q2["answer"] is False

    def test_blank(self):
        q = parse_question_block("1. 1KB 等于 1024____。\n答案：字节")
        assert q["qtype"] == "blank"
        assert q["answer"] == ["字节"]

    def test_shortanswer(self):
        q = parse_question_block("1. 请简述进程和线程的区别。\n答案：进程是资源分配单位，线程是调度单位。")
        assert q["qtype"] == "shortanswer"

    def test_unknown_requires_review(self):
        q = parse_question_block("1. 奇怪的题目没有答案")
        assert q["status"] in ("need_review", "failed", "ok")
        if q["qtype"] == "unknown":
            assert q["status"] == "need_review"


class TestParseValidate:
    def test_answer_mismatch_flagged(self):
        q = parse_question_block("1. 题？\nA. a\nB. b\n答案：Z")
        assert "answer_mismatch" in q["uncertain_fields"] or q["status"] == "need_review"

    def test_missing_answer_flagged(self):
        q = parse_question_block("1. 题？\nA. a\nB. b\nC. c\nD. d")
        assert q["status"] == "need_review"
        assert "answer" in q["uncertain_fields"]

    def test_validate_parsed(self):
        ok, _ = validate_parsed({
            "stem": "题目", "qtype": "single",
            "options": [{"label": "A", "content": "1"}, {"label": "B", "content": "2"}],
            "answer": "A",
        })
        assert ok
        ok2, msg = validate_parsed({"stem": "题目", "qtype": "unknown", "options": [], "answer": ""})
        assert not ok2
        ok3, msg3 = validate_parsed({
            "stem": "题目", "qtype": "single",
            "options": [{"label": "A", "content": "1"}, {"label": "B", "content": "2"}],
            "answer": "Z",
        })
        assert not ok3

    def test_qtype_label_not_stripped_from_stem(self):
        q = parse_question_block("1. 计算机的 CPU 主要负责什么？\nA. 存储\nB. 执行\n答案：B")
        assert q["stem"].startswith("计算机的 CPU")


class TestGrader:
    def test_single(self):
        assert grade_objective("single", "B", "B")[0] is True
        assert grade_objective("single", "A", "B")[0] is False

    def test_multiple_exact_set(self):
        assert grade_objective("multiple", ["A", "B", "D"], ["A", "B", "D"])[0] is True
        assert grade_objective("multiple", ["A", "B"], ["A", "B", "D"])[0] is False
        assert grade_objective("multiple", ["A", "B", "D"], ["A", "B"])[0] is False
        assert grade_objective("multiple", "ABD", ["A", "B", "D"])[0] is True

    def test_truefalse_normalize(self):
        assert normalize_bool("正确") is True
        assert normalize_bool("True") is True
        assert normalize_bool("错误") is False
        assert normalize_bool("false") is False
        assert grade_objective("truefalse", "正确", True)[0] is True
        assert grade_objective("truefalse", "False", False)[0] is True

    def test_blank_equivalents(self):
        ok, _ = grade_objective("blank", ["字节"], [["字节", "Bytes", "bytes"]])
        assert ok is True
        ok2, _ = grade_objective("blank", ["Bytes"], [["字节", "Bytes"]])
        assert ok2 is True
        ok3, _ = grade_objective("blank", ["比特"], [["字节"]])
        assert ok3 is False


class TestDedup:
    def test_hash_stable(self):
        assert content_hash("1. 测试题目", "single") == content_hash("测试题目", "single")

    def test_similarity(self):
        assert similarity("什么是操作系统？", "什么是操作系统？") == 1.0
        assert similarity("什么是操作系统？", "完全不同的句子内容") < 0.3

    def test_find_duplicate(self):
        existing = [(1, "什么是操作系统？", "single")]
        assert find_duplicate("什么是操作系统？", "single", existing) == 1
        assert find_duplicate("完全无关的新题目内容啊", "single", existing) is None


class TestGluedMarkers:
    """回归：【答案】【解析】等标记粘连在选项/题干行内时必须正确剥离。"""

    def test_glued_answer_explanation_in_last_option(self):
        raw = (
            "1. 中国共产党的最高理想和最终目标是（）。\n"
            "A. 实现社会主义现代化\nB. 建设中国特色社会主义\n"
            "C. 建设社会主义现代化强国\n"
            "D. 实现中华民族伟大复兴【答案】B【解析】党章总纲明确。"
        )
        q = parse_question_block(raw)
        assert len(q["options"]) == 4
        for o in q["options"]:
            assert "【答案】" not in o["content"] and "【解析】" not in o["content"]
        assert q["answer"] == "B"
        assert "党章" in q["explanation"]

    def test_glued_inline_colon_in_option(self):
        raw = (
            "2. 以下哪些属于操作系统？\n"
            "A. Windows\nB. Linux\nC. MySQL\nD. macOS 答案：ABD 解析：MySQL是数据库。"
        )
        q = parse_question_block(raw)
        assert len(q["options"]) == 4
        for o in q["options"]:
            assert "答案" not in o["content"]
        assert q["answer"] == ["A", "B", "D"]

    def test_glued_markers_in_truefalse_stem(self):
        raw = "3. FIFO 是先进先出算法。【答案】正确【解析】FIFO即First In First Out。"
        q = parse_question_block(raw)
        assert "【答案】" not in q["stem"]
        assert q["answer"] in (True, "正确", "对")
        assert "FIFO" in q["explanation"]

    def test_normal_format_not_broken(self):
        raw = (
            "4. CPU 主要负责什么？\n"
            "A. 存储数据\nB. 执行指令\nC. 显示画面\nD. 连接网络\n"
            "答案：B\n解析：CPU负责运算和控制。"
        )
        q = parse_question_block(raw)
        assert len(q["options"]) == 4
        assert q["answer"] == "B"
        assert "运算" in q["explanation"]
