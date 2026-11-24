"""全链路 API 验收测试（核心链路）：注册→建题库→批量导入→识别→确认→刷题→判题→错题→AI 降级。"""
import json
import sys
import httpx

BASE = "http://127.0.0.1:8017"
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name} {extra}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def main():
    c = httpx.Client(base_url=BASE, timeout=30)

    print("== 1. 注册/登录 ==")
    r = c.post("/api/auth/register", json={"username": "alice", "password": "secret123", "nickname": "Alice"})
    check("注册 alice", r.status_code == 200, f"({r.status_code})")
    token_a = r.json()["access_token"]
    check("首个用户是管理员", r.json()["user"]["role"] == "admin")
    ha = {"Authorization": f"Bearer {token_a}"}

    r = c.post("/api/auth/register", json={"username": "bob", "password": "secret123"})
    token_b = r.json()["access_token"]
    hb = {"Authorization": f"Bearer {token_b}"}
    check("注册 bob", r.status_code == 200)

    print("== 2. 创建题库 ==")
    r = c.post("/api/banks", headers=ha, json={"name": "操作系统", "category": "操作系统", "description": "OS 题库"})
    check("创建题库", r.status_code == 200, f"bank_id={r.json()['id']}")
    bank_id = r.json()["id"]

    r = c.get(f"/api/banks/{bank_id}", headers=hb)
    check("bob 无权访问私有题库", r.status_code == 403)

    print("== 3. 文本批量导入 → 识别 → 确认 ==")
    raw = """1. 计算机的 CPU 主要负责什么？
A. 存储数据
B. 执行指令
C. 显示画面
D. 连接网络
答案：B
解析：CPU 是中央处理器，负责执行指令。

2. 以下哪些属于操作系统？
A. Windows
B. Linux
C. MySQL
D. macOS
答案：A、B、D

3. FIFO 是先进先出页面置换算法。
答案：正确

4. 在计算机中，1KB 等于 1024____。
答案：字节

5. 请简述进程和线程的主要区别。
答案：进程是资源分配的基本单位，线程是CPU调度的基本单位。"""
    r = c.post("/api/import/parse", headers=ha, json={"raw_text": raw, "bank_id": bank_id})
    check("解析接口 200", r.status_code == 200)
    d = r.json()
    check("拆出 5 道题", d["total"] == 5, f"total={d['total']}")
    types = [q["qtype"] for q in d["questions"]]
    check("题型识别正确", types == ["single", "multiple", "truefalse", "blank", "shortanswer"], str(types))
    check("单选答案 B", d["questions"][0]["answer"] == "B")
    check("多选答案 ABD", d["questions"][1]["answer"] == ["A", "B", "D"])
    check("判断答案 True", d["questions"][2]["answer"] is True)
    check("填空答案", d["questions"][3]["answer"] == ["字节"])
    task_id = d["task_id"]

    r = c.post("/api/import/confirm", headers=ha, json={
        "task_id": task_id, "bank_id": bank_id,
        "questions": [q.model_dump() if hasattr(q, "model_dump") else q for q in d["questions"]],
        "skip_duplicates": True, "include_unknown": True,
    })
    check("确认导入", r.status_code == 200, f"imported={r.json()['imported']}")
    check("导入 5 题", r.json()["imported"] == 5)

    # 重复导入检测
    r = c.post("/api/import/parse", headers=ha, json={"raw_text": raw, "bank_id": bank_id})
    d2 = r.json()
    check("重复识别", d2["duplicate"] >= 4, f"dup={d2['duplicate']}")
    r = c.post("/api/import/confirm", headers=ha, json={
        "bank_id": bank_id, "questions": d2["questions"],
        "skip_duplicates": True, "include_unknown": True,
    })
    check("重复导入被跳过", r.json()["skipped_duplicate"] >= 4 and r.json()["imported"] == 0,
          f"imported={r.json()['imported']} skipped={r.json()['skipped_duplicate']}")

    r = c.get(f"/api/banks/{bank_id}/questions", headers=ha)
    check("题目数量为 5", r.json()["total"] == 5, f"total={r.json()['total']}")

    print("== 4. 生成练习 → 作答 → 判题 ==")
    r = c.post("/api/practice/sessions", headers=ha, json={
        "bank_id": bank_id, "mode": "sequential", "count": 5, "show_answer_mode": "immediate"})
    check("创建练习", r.status_code == 200)
    sess = r.json()
    sess_id = sess["id"]

    r = c.get(f"/api/practice/sessions/{sess_id}/questions", headers=ha)
    qs = r.json()["questions"]
    check("试卷含 5 题", len(qs) == 5)
    check("未显示答案字段为空", qs[0].get("explanation") == "" or "answer" not in qs[0] or qs[0].get("answer") is None)

    answers = {0: "B", 1: ["A", "B", "D"], 2: True, 3: ["字节"], 4: "进程是资源分配的基本单位，线程是CPU调度的基本单位"}
    results = []
    for i, q in enumerate(qs):
        r = c.post(f"/api/practice/sessions/{sess_id}/answer", headers=ha, json={
            "question_id": q["id"], "answer": answers[i], "time_spent": 10})
        results.append(r.json())
        check(f"作答第{i+1}题 200", r.status_code == 200)

    check("单选判对", results[0]["is_correct"] is True)
    check("多选判对", results[1]["is_correct"] is True)
    check("判断判对", results[2]["is_correct"] is True)
    check("填空判对", results[3]["is_correct"] is True)

    # 错误答案 → 错题本
    r = c.post("/api/practice/sessions", headers=ha, json={"bank_id": bank_id, "mode": "sequential", "count": 5})
    sess2 = r.json()["id"]
    r = c.get(f"/api/practice/sessions/{sess2}/questions", headers=ha)
    qs2 = r.json()["questions"]
    r = c.post(f"/api/practice/sessions/{sess2}/answer", headers=ha, json={
        "question_id": qs2[0]["id"], "answer": "A"})  # 错误
    check("错误答案判错", r.json()["is_correct"] is False)

    r = c.get("/api/practice/wrong", headers=ha)
    check("错题本有记录", r.json()["total"] >= 1, f"total={r.json()['total']}")
    wrong_id = r.json()["items"][0]["id"]

    r = c.put(f"/api/practice/wrong/{wrong_id}", headers=ha, json={"mastery": "need_review"})
    check("更新掌握度", r.status_code == 200)

    print("== 5. 收藏 ==")
    r = c.post("/api/practice/favorites", headers=ha, json={"question_id": qs2[0]["id"], "note": "重点"})
    check("收藏成功", r.status_code == 200)
    r = c.get("/api/practice/favorites", headers=ha)
    check("收藏列表", r.json()["total"] >= 1)

    print("== 6. 模拟考试 ==")
    r = c.post("/api/practice/sessions", headers=ha, json={
        "bank_id": bank_id, "mode": "exam", "count": 5, "duration_limit": 1800, "show_answer_mode": "after_submit"})
    exam = r.json()
    r = c.get(f"/api/practice/sessions/{exam['id']}/questions", headers=ha)
    check("考试不显示答案", r.json()["show_answers"] is False)
    r = c.post(f"/api/practice/sessions/{exam['id']}/submit", headers=ha, json={"answers": []})
    check("交卷成功", r.status_code == 200)
    r = c.get(f"/api/practice/sessions/{exam['id']}/result", headers=ha)
    check("成绩报告", r.status_code == 200 and "summary" in r.json())

    print("== 7. AI 降级（未配置 Key）==")
    r = c.get("/api/ai/status", headers=ha)
    check("AI 状态可查", r.status_code == 200)
    check("未配置标记", r.json()["configured"] is False)
    r = c.post(f"/api/ai/explain?question_id={qs[0]['id']}", headers=ha)
    check("AI 解析返回占位标记", r.json()["is_placeholder"] is True)
    check("占位内容明示", "开发占位" in r.json()["content"] or "非真实" in r.json()["content"])
    r = c.post("/api/ai/chat", headers=ha, json={"message": "这道题为什么选 B？", "context_type": "question", "context_ref": {"question_id": qs[0]["id"]}})
    check("AI 聊通", r.status_code == 200 and r.json()["is_placeholder"] is True)

    print("== 8. 多用户数据隔离 ==")
    r = c.get("/api/practice/sessions", headers=hb)
    bob_sessions = r.json()
    check("bob 看不到 alice 的练习", all(s["id"] != sess_id for s in bob_sessions))
    r = c.get("/api/practice/wrong", headers=hb)
    check("bob 错题本为空", r.json()["total"] == 0)
    r = c.get("/api/banks", headers=hb)
    check("bob 题库列表为空/无私有库", all(b["id"] != bank_id for b in r.json()))

    print("== 9. 共享题库 ==")
    r = c.post(f"/api/banks/{bank_id}/share", headers=ha, json={"username": "bob", "can_edit": False})
    check("共享给 bob", r.status_code == 200)
    r = c.get(f"/api/banks/{bank_id}", headers=hb)
    check("bob 可访问共享题库", r.status_code == 200)
    r = c.post(f"/api/banks/{bank_id}/questions", headers=hb, json={
        "qtype": "single", "stem": "test", "options": [{"label": "A", "content": "1"}, {"label": "B", "content": "2"}], "answer": "A"})
    check("bob 只读不能编辑", r.status_code == 403)

    print("== 10. 统计 ==")
    r = c.get("/api/stats/summary", headers=ha)
    s = r.json()
    check("统计有数据", s["total_answered"] >= 5, f"answered={s['total_answered']}")
    check("题型统计存在", "single" in s["by_type"])
    check("每日趋势 30 天", len(s["daily_trend"]) == 30)

    print("== 11. 文件导入（CSV）==")
    csv_content = "题干,A,B,C,D,答案,解析\nOS的功能是什么？,管理硬件,管理软件,编译代码,播放视频,A,OS管理硬件与软件资源\n".encode("utf-8")
    r = c.post("/api/import/file", headers=ha, params={"bank_id": bank_id},
               files={"file": ("test.csv", csv_content, "text/csv")})
    check("CSV 导入解析", r.status_code == 200 and r.json()["total"] >= 1,
          f"total={r.json().get('total') if r.status_code == 200 else r.text[:100]}")

    print("== 12. 批量操作去重 ==")
    r = c.post(f"/api/banks/{bank_id}/questions/batch", headers=ha, json={"ids": [], "action": "dedup"})
    check("全库去重", r.status_code == 200)

    print("== 13. 题目编辑/删除 ==")
    r = c.get(f"/api/banks/{bank_id}/questions", headers=ha)
    q1 = r.json()["items"][0]
    r = c.put(f"/api/questions/{q1['id']}", headers=ha, json={"stem": "修改后的题干", "difficulty": 3})
    check("编辑题目", r.status_code == 200 and r.json()["stem"] == "修改后的题干")
    r = c.post(f"/api/banks/{bank_id}/questions", headers=ha, json={
        "qtype": "truefalse", "stem": "新增判断题测试", "answer": True, "explanation": "test"})
    new_qid = r.json()["id"]
    r = c.delete(f"/api/questions/{new_qid}", headers=ha)
    check("删除题目", r.status_code == 200)

    print(f"\n========== 结果: PASS={PASS} FAIL={FAIL} ==========")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
