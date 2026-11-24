"""API 级 pytest：权限控制、答题记录持久化、重复导入（TestClient，无需启动服务）。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db, engine, Base

RAW = """1. 选择题一？
A. 甲
B. 乙
C. 丙
D. 丁
答案：A

2. 多选题二？
A. 一
B. 二
C. 三
D. 四
答案：AC

3. 判断题三。
答案：错误"""


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def tokens(client):
    a = client.post("/api/auth/register", json={"username": "u1", "password": "pass123"}).json()
    b = client.post("/api/auth/register", json={"username": "u2", "password": "pass123"}).json()
    return {"a": f"Bearer {a['access_token']}", "b": f"Bearer {b['access_token']}"}


def auth(h):
    return {"Authorization": h}


class TestPermission:
    def test_private_bank_isolated(self, client, tokens):
        r = client.post("/api/banks", headers=auth(tokens["a"]), json={"name": "私有库"})
        bid = r.json()["id"]
        r = client.get(f"/api/banks/{bid}", headers=auth(tokens["b"]))
        assert r.status_code == 403

    def test_share_readonly(self, client, tokens):
        bid = client.post("/api/banks", headers=auth(tokens["a"]), json={"name": "共享库"}).json()["id"]
        client.post(f"/api/banks/{bid}/share", headers=auth(tokens["a"]), json={"username": "u2", "can_edit": False})
        assert client.get(f"/api/banks/{bid}", headers=auth(tokens["b"])).status_code == 200
        r = client.post(f"/api/banks/{bid}/questions", headers=auth(tokens["b"]), json={
            "qtype": "single", "stem": "x", "options": [{"label": "A", "content": "1"}, {"label": "B", "content": "2"}], "answer": "A"})
        assert r.status_code == 403

    def test_admin_required(self, client, tokens):
        # u1 是首个用户（管理员），u2 不是
        assert client.get("/api/settings/ai", headers=auth(tokens["b"])).status_code == 403
        assert client.get("/api/settings/ai", headers=auth(tokens["a"])).status_code == 200

    def test_unauthorized(self, client):
        assert client.get("/api/banks").status_code == 401


class TestImport:
    def test_parse_and_confirm(self, client, tokens):
        bid = client.post("/api/banks", headers=auth(tokens["a"]), json={"name": "导入库"}).json()["id"]
        r = client.post("/api/import/parse", headers=auth(tokens["a"]), json={"raw_text": RAW, "bank_id": bid})
        d = r.json()
        assert d["total"] == 3
        assert [q["qtype"] for q in d["questions"]] == ["single", "multiple", "truefalse"]
        r = client.post("/api/import/confirm", headers=auth(tokens["a"]), json={
            "bank_id": bid, "questions": d["questions"], "skip_duplicates": True, "include_unknown": True})
        assert r.json()["imported"] == 3

    def test_duplicate_import_skipped(self, client, tokens):
        bid = client.post("/api/banks", headers=auth(tokens["a"]), json={"name": "去重库"}).json()["id"]
        d = client.post("/api/import/parse", headers=auth(tokens["a"]), json={"raw_text": RAW, "bank_id": bid}).json()
        client.post("/api/import/confirm", headers=auth(tokens["a"]), json={
            "bank_id": bid, "questions": d["questions"], "skip_duplicates": True, "include_unknown": True})
        d2 = client.post("/api/import/parse", headers=auth(tokens["a"]), json={"raw_text": RAW, "bank_id": bid}).json()
        assert d2["duplicate"] == 3
        r = client.post("/api/import/confirm", headers=auth(tokens["a"]), json={
            "bank_id": bid, "questions": d2["questions"], "skip_duplicates": True, "include_unknown": True})
        assert r.json()["imported"] == 0
        assert r.json()["skipped_duplicate"] == 3


class TestPracticePersist:
    def _make_bank_with_questions(self, client, h):
        bid = client.post("/api/banks", headers=h, json={"name": "刷题库"}).json()["id"]
        d = client.post("/api/import/parse", headers=h, json={"raw_text": RAW, "bank_id": bid}).json()
        client.post("/api/import/confirm", headers=h, json={
            "bank_id": bid, "questions": d["questions"], "skip_duplicates": True, "include_unknown": True})
        return bid

    def test_answers_persist_across_sessions(self, client, tokens):
        h = auth(tokens["a"])
        bid = self._make_bank_with_questions(client, h)
        sess = client.post("/api/practice/sessions", headers=h,
                           json={"bank_id": bid, "mode": "sequential", "count": 5}).json()
        qs = client.get(f"/api/practice/sessions/{sess['id']}/questions", headers=h).json()["questions"]
        r = client.post(f"/api/practice/sessions/{sess['id']}/answer", headers=h,
                        json={"question_id": qs[0]["id"], "answer": "A"})
        assert r.json()["is_correct"] is True
        # 刷新后仍然存在（从数据库重新读取）
        result = client.get(f"/api/practice/sessions/{sess['id']}/result", headers=h).json()
        assert result["summary"]["answered"] == 1
        assert result["details"][0]["user_answer"] == "A"

    def test_wrong_question_recorded(self, client, tokens):
        h = auth(tokens["a"])
        bid = self._make_bank_with_questions(client, h)
        sess = client.post("/api/practice/sessions", headers=h,
                           json={"bank_id": bid, "mode": "sequential", "count": 5}).json()
        qs = client.get(f"/api/practice/sessions/{sess['id']}/questions", headers=h).json()["questions"]
        client.post(f"/api/practice/sessions/{sess['id']}/answer", headers=h,
                    json={"question_id": qs[0]["id"], "answer": "B"})  # 错误
        wrong = client.get("/api/practice/wrong", headers=h).json()
        assert wrong["total"] >= 1

    def test_user_data_isolated(self, client, tokens):
        ha, hb = auth(tokens["a"]), auth(tokens["b"])
        bid = self._make_bank_with_questions(client, ha)
        sess = client.post("/api/practice/sessions", headers=ha,
                           json={"bank_id": bid, "mode": "sequential", "count": 5}).json()
        client.post(f"/api/practice/sessions/{sess['id']}/submit", headers=ha, json={"answers": []})
        bob_sessions = client.get("/api/practice/sessions", headers=hb).json()
        assert all(s["id"] != sess["id"] for s in bob_sessions)
        bob_stats = client.get("/api/stats/summary", headers=hb).json()
        assert bob_stats["total_answered"] == 0


class TestLoginRecords:
    """登录数据入库：登录/注册/失败事件持久化到 login_records 表。"""

    def test_register_and_login_recorded(self, client):
        r = client.post("/api/auth/register", json={"username": "lr_user", "password": "pass123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        records = client.get("/api/auth/login-records", headers=h).json()
        assert any(rec["event"] == "register" for rec in records)
        # 再登录一次
        r2 = client.post("/api/auth/login", json={"username": "lr_user", "password": "pass123"})
        assert r2.status_code == 200
        records = client.get("/api/auth/login-records", headers=h).json()
        assert any(rec["event"] == "login" for rec in records)
        # 最近登录时间已更新
        me = client.get("/api/auth/me", headers=h).json()
        assert me["last_login_at"] is not None

    def test_failed_login_recorded(self, client):
        client.post("/api/auth/register", json={"username": "lr_fail", "password": "pass123"})
        r = client.post("/api/auth/login", json={"username": "lr_fail", "password": "wrongpwd"})
        assert r.status_code == 400
        # 用正确密码登录后能看到失败记录
        r = client.post("/api/auth/login", json={"username": "lr_fail", "password": "pass123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        records = client.get("/api/auth/login-records", headers=h).json()
        assert any(rec["event"] == "failed" for rec in records)

    def test_login_records_isolated(self, client, tokens):
        ha, hb = auth(tokens["a"]), auth(tokens["b"])
        ra = client.get("/api/auth/login-records", headers=ha).json()
        rb = client.get("/api/auth/login-records", headers=hb).json()
        assert all(rec["username"] == "u1" for rec in ra)
        assert all(rec["username"] == "u2" for rec in rb)


class TestWrongMastery:
    """错题掌握度：连对 2 次→基本掌握，连对 3 次→已掌握，答错清零连对。"""

    def _make_bank(self, client, h, name):
        bid = client.post("/api/banks", headers=h, json={"name": name}).json()["id"]
        d = client.post("/api/import/parse", headers=h, json={"raw_text": RAW, "bank_id": bid}).json()
        client.post("/api/import/confirm", headers=h, json={
            "bank_id": bid, "questions": d["questions"], "skip_duplicates": True, "include_unknown": True})
        return bid

    def _answer(self, client, h, sess, qid, ans):
        return client.post(f"/api/practice/sessions/{sess['id']}/answer", headers=h,
                           json={"question_id": qid, "answer": ans}).json()

    def _wrong_row(self, client, h, qid):
        items = client.get("/api/practice/wrong?limit=200", headers=h).json()["items"]
        return next(w for w in items if w["question_id"] == qid)

    def _new_session(self, client, h, bid):
        return client.post("/api/practice/sessions", headers=h,
                           json={"bank_id": bid, "mode": "sequential", "count": 5,
                                 "selection": "from_start"}).json()

    def test_streak_upgrades_mastery(self, client, tokens):
        h = auth(tokens["a"])
        bid = self._make_bank(client, h, "掌握度库")
        all_q = client.get(f"/api/banks/{bid}/questions", headers=h).json()["items"]
        qid = all_q[0]["id"]           # 单选题，正确答案 A
        # 先做错入册
        sess = self._new_session(client, h, bid)
        self._answer(client, h, sess, qid, "B")
        w = self._wrong_row(client, h, qid)
        assert w["mastery"] == "not_mastered" and w["streak"] == 0
        # 连对 1 次：不升级
        self._answer(client, h, sess, qid, "A")
        w = self._wrong_row(client, h, qid)
        assert w["mastery"] == "not_mastered" and w["streak"] == 1
        # 连对 2 次：基本掌握
        self._answer(client, h, sess, qid, "A")
        w = self._wrong_row(client, h, qid)
        assert w["mastery"] == "basically" and w["streak"] == 2
        # 连对 3 次：已掌握
        self._answer(client, h, sess, qid, "A")
        w = self._wrong_row(client, h, qid)
        assert w["mastery"] == "mastered" and w["streak"] == 3

    def test_wrong_resets_streak(self, client, tokens):
        h = auth(tokens["a"])
        bid = self._make_bank(client, h, "连对清零库")
        all_q = client.get(f"/api/banks/{bid}/questions", headers=h).json()["items"]
        qid = all_q[0]["id"]
        sess = self._new_session(client, h, bid)
        self._answer(client, h, sess, qid, "B")   # 入册
        self._answer(client, h, sess, qid, "A")
        self._answer(client, h, sess, qid, "A")   # 连对 2 → 基本掌握
        # 再答错：连对清零、掌握度降回需要复习
        self._answer(client, h, sess, qid, "B")
        w = self._wrong_row(client, h, qid)
        assert w["streak"] == 0
        assert w["mastery"] == "need_review"
        # 重新连对 2 次只能回到基本掌握
        self._answer(client, h, sess, qid, "A")
        self._answer(client, h, sess, qid, "A")
        w = self._wrong_row(client, h, qid)
        assert w["mastery"] == "basically" and w["streak"] == 2


class TestSmartSelection:
    """默认智能选题：未做 → 错题 → 已做对；从头开始需显式选择。"""

    def _make_bank(self, client, h, name):
        bid = client.post("/api/banks", headers=h, json={"name": name}).json()["id"]
        d = client.post("/api/import/parse", headers=h, json={"raw_text": RAW, "bank_id": bid}).json()
        client.post("/api/import/confirm", headers=h, json={
            "bank_id": bid, "questions": d["questions"], "skip_duplicates": True, "include_unknown": True})
        return bid

    def test_default_prioritizes_unseen(self, client, tokens):
        h = auth(tokens["a"])
        bid = self._make_bank(client, h, "智能选题库")
        all_q = client.get(f"/api/banks/{bid}/questions", headers=h).json()["items"]
        first_id = all_q[0]["id"]
        # 先做第一题（做对）
        sess = client.post("/api/practice/sessions", headers=h,
                           json={"bank_id": bid, "mode": "sequential", "count": 5}).json()
        client.post(f"/api/practice/sessions/{sess['id']}/answer", headers=h,
                    json={"question_id": first_id, "answer": "A"})
        # 再开新会话（默认 selection=smart）：第一题（已做对）应排到后面
        sess2 = client.post("/api/practice/sessions", headers=h,
                            json={"bank_id": bid, "mode": "sequential", "count": 5}).json()
        ids = sess2["question_ids"]
        assert first_id not in ids[:2], f"已做对的题不应排在最前: {ids}"
        assert sess2["filter_meta"].get("selection") == "smart"

    def test_from_start_keeps_original_order(self, client, tokens):
        h = auth(tokens["a"])
        bid = self._make_bank(client, h, "从头开始库")
        all_q = client.get(f"/api/banks/{bid}/questions", headers=h).json()["items"]
        original = [q["id"] for q in all_q]
        sess = client.post("/api/practice/sessions", headers=h,
                           json={"bank_id": bid, "mode": "sequential", "count": 5,
                                 "selection": "from_start"}).json()
        assert sess["question_ids"] == original[:len(sess["question_ids"])]

    def test_wrong_question_prioritized(self, client, tokens):
        h = auth(tokens["a"])
        bid = self._make_bank(client, h, "错题优先库")
        all_q = client.get(f"/api/banks/{bid}/questions", headers=h).json()["items"]
        # 把后一题做错，前一题做对
        q_first, q_last = all_q[0], all_q[-1]
        sess = client.post("/api/practice/sessions", headers=h,
                           json={"bank_id": bid, "mode": "sequential", "count": 5,
                                 "selection": "from_start"}).json()
        client.post(f"/api/practice/sessions/{sess['id']}/answer", headers=h,
                    json={"question_id": q_first["id"], "answer": "A"})       # 对
        client.post(f"/api/practice/sessions/{sess['id']}/answer", headers=h,
                    json={"question_id": q_last["id"], "answer": "Z"})        # 错
        sess2 = client.post("/api/practice/sessions", headers=h,
                            json={"bank_id": bid, "mode": "sequential", "count": 5}).json()
        ids = sess2["question_ids"]
        # 智能选题：未做 + 错题都排在「已做对」之前
        assert q_last["id"] in ids
        if q_first["id"] in ids:
            assert ids.index(q_last["id"]) < ids.index(q_first["id"]), \
                "错题应排在已做对的题之前"
