"""刷题 / 判题 / 模拟考试 / 错题本 / 收藏 路由。"""
import json
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, QuestionBank, Question, QuestionOption, BlankAnswer,
    PracticeSession, PracticeAnswer, WrongQuestion, Favorite,
    SessionMode, SessionStatus, WrongMastery, QuestionType, AnswerReviewStatus,
)
from ..schemas import (
    SessionCreateIn, SessionOut, SubmitAnswerIn, AnswerResult,
    SessionSubmitIn, WrongUpdateIn, FavoriteIn,
)
from ..deps import get_current_user, check_bank_access
from ..services.grader import grade_objective, grade_short_answer_rule, grade_calculation, normalize_bool
from ..services import ai_client as ai

router = APIRouter(prefix="/api/practice", tags=["practice"])

INTERVAL_DAYS = [1, 2, 4, 7, 15, 30]


def _session_out(db: Session, s: PracticeSession) -> SessionOut:
    out = SessionOut.model_validate(s)
    bank = db.query(QuestionBank).get(s.bank_id)
    out.bank_name = bank.name if bank else ""
    return out


def _question_payload(db: Session, q: Question, include_answer: bool = False) -> Dict[str, Any]:
    from .questions import _extract_answer
    data = {
        "id": q.id,
        "bank_id": q.bank_id,
        "chapter_id": q.chapter_id,
        "qtype": q.qtype,
        "stem": q.stem,
        "explanation": q.explanation if include_answer else "",
        "difficulty": q.difficulty,
        "knowledge_points": q.knowledge_points or [],
        "options": [
            {"id": o.id, "label": o.label, "content": o.content,
             "is_correct": o.is_correct if include_answer else None}
            for o in q.options if o.label != "ANS"
        ],
    }
    if include_answer:
        data["answer"] = _extract_answer(q)
        data["explanation"] = q.explanation
        data["review_status"] = q.review_status
    return data


def _get_answer(db: Session, q: Question) -> Any:
    from .questions import _extract_answer
    return _extract_answer(q)


@router.post("/sessions", response_model=SessionOut)
def create_session(data: SessionCreateIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(data.bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank)

    if data.mode not in [m.value for m in SessionMode]:
        raise HTTPException(status_code=400, detail="练习模式无效")

    q = db.query(Question).filter(
        Question.bank_id == data.bank_id,
        Question.is_draft == False,  # noqa: E712
    )
    if data.mode == SessionMode.specialized and data.qtypes:
        q = q.filter(Question.qtype.in_(data.qtypes))
    elif data.mode == SessionMode.chapter and data.chapter_id:
        q = q.filter(Question.chapter_id == data.chapter_id)
    elif data.mode == SessionMode.topic and data.knowledge_point:
        q = q.filter(Question.knowledge_points.contains(data.knowledge_point))
    elif data.mode == SessionMode.wrong_retry:
        wrong_ids = db.query(WrongQuestion.question_id).filter(
            WrongQuestion.user_id == user.id, WrongQuestion.bank_id == data.bank_id
        )
        q = q.filter(Question.id.in_(wrong_ids))
    elif data.mode == SessionMode.favorite:
        fav_ids = db.query(Favorite.question_id).filter(
            Favorite.user_id == user.id, Favorite.bank_id == data.bank_id
        )
        q = q.filter(Question.id.in_(fav_ids))
    if data.qtypes and data.mode in (SessionMode.random, SessionMode.sequential, SessionMode.exam):
        q = q.filter(Question.qtype.in_(data.qtypes))

    all_ids = [row[0] for row in q.with_entities(Question.id).all()]
    if not all_ids:
        raise HTTPException(status_code=400, detail="没有符合条件的题目，请先导入题目或调整筛选条件")

    selection = getattr(data, "selection", "smart") or "smart"
    if data.mode in (SessionMode.wrong_retry, SessionMode.favorite):
        # 错题重练 / 收藏练习语义明确，按原顺序取样
        selection = "from_start"

    if selection == "smart":
        # 智能选题：未做过的题优先 → 做错的题（错得越多越靠前）→ 已做对的题
        answered_rows = db.query(PracticeAnswer.question_id, PracticeAnswer.is_correct).filter(
            PracticeAnswer.user_id == user.id,
            PracticeAnswer.question_id.in_(all_ids),
        ).all()
        answered_map = {qid: bool(ok) for qid, ok in answered_rows}
        wrong_rows = db.query(WrongQuestion.question_id, WrongQuestion.wrong_count).filter(
            WrongQuestion.user_id == user.id,
            WrongQuestion.question_id.in_(all_ids),
        ).all()
        wrong_map = {qid: cnt or 1 for qid, cnt in wrong_rows}

        unseen = [qid for qid in all_ids if qid not in answered_map]
        wrong_ids = sorted(
            [qid for qid in all_ids if qid in answered_map and not answered_map[qid] or qid in wrong_map and qid not in unseen],
            key=lambda x: -wrong_map.get(x, 0),
        )
        wrong_ids = [qid for qid in wrong_ids if qid not in unseen]
        seen_correct = [qid for qid in all_ids if qid in answered_map and answered_map[qid] and qid not in wrong_map and qid not in unseen]
        ordered = unseen + wrong_ids + seen_correct
    else:
        ordered = list(all_ids)

    if data.mode in (SessionMode.random, SessionMode.exam):
        # 随机/考试：在智能优先级的前半段（未做+错题）优先随机抽取
        count = data.count if data.count and data.count > 0 else min(10, len(ordered))
        pool = ordered[: max(count * 2, count)] if selection == "smart" else ordered
        ids = random.sample(pool, min(count, len(pool)))
    else:
        # sequential/chapter/topic/specialized：smart=未做错题优先；from_start=从头按题库顺序
        ids = ordered[: data.count] if data.count and data.count < len(ordered) else ordered

    session = PracticeSession(
        user_id=user.id,
        bank_id=data.bank_id,
        mode=data.mode,
        question_ids=ids,
        show_answer_mode=data.show_answer_mode if data.mode != SessionMode.exam else "after_submit",
        duration_limit=data.duration_limit,
        total_questions=len(ids),
        filter_meta={
            "qtypes": data.qtypes, "chapter_id": data.chapter_id,
            "knowledge_point": data.knowledge_point, "count": data.count,
            "selection": selection,
        },
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.get("/sessions")
def list_sessions(
    status: Optional[str] = None,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(PracticeSession).filter(PracticeSession.user_id == user.id)
    if status:
        q = q.filter(PracticeSession.status == status)
    sessions = q.order_by(PracticeSession.started_at.desc()).limit(limit).all()
    return [_session_out(db, s).model_dump() for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    s = db.query(PracticeSession).get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="练习不存在")
    if s.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问该练习")
    return _session_out(db, s)


@router.get("/sessions/{session_id}/questions")
def session_questions(
    session_id: int,
    with_answers: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回试卷题目。考试未交卷时隐藏答案。"""
    s = db.query(PracticeSession).get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="练习不存在")
    if s.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问该练习")

    show = with_answers
    if s.mode == SessionMode.exam.value and s.status == SessionStatus.in_progress.value:
        show = False
    elif not with_answers and s.show_answer_mode == "immediate" and s.status == SessionStatus.submitted.value:
        show = True

    items = []
    for qid in s.question_ids:
        q = db.query(Question).get(qid)
        if q:
            items.append(_question_payload(db, q, include_answer=show))
    return {
        "session": _session_out(db, s).model_dump(),
        "questions": items,
        "show_answers": show,
    }


@router.post("/sessions/{session_id}/answer", response_model=AnswerResult)
def submit_answer(session_id: int, data: SubmitAnswerIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    s = db.query(PracticeSession).get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="练习不存在")
    if s.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该练习")
    if s.status != SessionStatus.in_progress.value:
        raise HTTPException(status_code=400, detail="练习已结束")
    if data.question_id not in s.question_ids:
        raise HTTPException(status_code=400, detail="题目不属于该练习")

    q = db.query(Question).get(data.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    correct_answer = _get_answer(db, q)
    user_answer = data.answer

    # 草稿模式：只保存不判题
    if data.draft_only:
        answers_map = s.answers_map or {}
        answers_map[str(data.question_id)] = user_answer
        s.answers_map = answers_map
        db.commit()
        return AnswerResult(question_id=q.id, user_answer=user_answer, qtype=q.qtype)

    is_correct: Optional[bool] = None
    note = ""
    ai_graded = False

    if q.qtype in (QuestionType.single.value, QuestionType.multiple.value,
                   QuestionType.truefalse.value, QuestionType.blank.value):
        is_correct, note = grade_objective(q.qtype, user_answer, correct_answer)
    elif q.qtype == QuestionType.calculation.value:
        r, note = grade_calculation(str(user_answer or ""), correct_answer)
        is_correct = r
        if r is None:
            ai_graded = True
            note = "【辅助评分 · 非绝对判定】" + note
    else:  # shortanswer
        kws = [w for w in (q.knowledge_points or []) if w]
        if q.explanation:
            kws += [w for w in q.explanation.replace("。", " ").split() if len(w) >= 2][:5]
        r, note = grade_short_answer_rule(str(user_answer or ""), kws)
        is_correct = r
        if r is None:
            # 尝试 AI 辅助评分
            client = ai.AIClient()
            if client.is_configured:
                gr = ai.grade_subjective(client, {
                    "stem": q.stem, "answer": correct_answer, "explanation": q.explanation,
                }, str(user_answer or ""))
                is_correct = gr.get("is_correct")
                ai_graded = True
                note = gr.get("note", "")
            else:
                note = "主观题需人工或 AI 评分。" + note
                ai_graded = False

    # 保存作答记录（同一题重复作答覆盖）
    record = db.query(PracticeAnswer).filter(
        PracticeAnswer.session_id == s.id, PracticeAnswer.question_id == q.id
    ).first()
    if record:
        record.user_answer = json.dumps(user_answer, ensure_ascii=False, default=str)
        record.correct_answer = json.dumps(correct_answer, ensure_ascii=False, default=str)
        record.is_correct = is_correct
        record.is_ai_graded = ai_graded
        record.ai_grade_note = note
        record.time_spent = data.time_spent
        record.submitted_at = datetime.utcnow()
    else:
        record = PracticeAnswer(
            session_id=s.id,
            question_id=q.id,
            user_id=user.id,
            user_answer=json.dumps(user_answer, ensure_ascii=False, default=str),
            correct_answer=json.dumps(correct_answer, ensure_ascii=False, default=str),
            is_correct=is_correct,
            is_ai_graded=ai_graded,
            ai_grade_note=note,
            time_spent=data.time_spent,
        )
        db.add(record)

    answers_map = s.answers_map or {}
    answers_map[str(data.question_id)] = user_answer
    s.answers_map = answers_map

    # 错题本（客观题明确判错时）
    if is_correct is False:
        _update_wrong(db, user, q, bank_id=s.bank_id, correct=False)
    elif is_correct is True:
        _update_wrong(db, user, q, bank_id=s.bank_id, correct=True)

    db.commit()

    show_now = s.show_answer_mode == "immediate" and s.mode != SessionMode.exam.value
    return AnswerResult(
        question_id=q.id,
        is_correct=is_correct if show_now else None,
        correct_answer=correct_answer if show_now else None,
        user_answer=user_answer,
        explanation=q.explanation if show_now else "",
        ai_graded=ai_graded,
        grade_note=note if show_now or ai_graded else "",
        qtype=q.qtype,
    )


def _update_wrong(db: Session, user: User, q: Question, bank_id: int, correct: bool):
    w = db.query(WrongQuestion).filter(
        WrongQuestion.user_id == user.id, WrongQuestion.question_id == q.id
    ).first()
    if correct:
        if w:
            w.correct_count += 1
            w.streak = (w.streak or 0) + 1
            w.review_stage = min(w.review_stage + 1, len(INTERVAL_DAYS) - 1)
            days = INTERVAL_DAYS[w.review_stage]
            w.next_review_at = datetime.utcnow() + timedelta(days=days)
            # 掌握度自动升级：连对 2 次 → 基本掌握；连对 3 次 → 已掌握
            if w.streak >= 3:
                w.mastery = WrongMastery.mastered.value
            elif w.streak >= 2 and w.mastery in (WrongMastery.not_mastered.value, WrongMastery.need_review.value):
                w.mastery = WrongMastery.basically.value
    else:
        if w:
            w.wrong_count += 1
            w.streak = 0  # 答错清零连对
            w.last_wrong_at = datetime.utcnow()
            w.review_stage = 0
            w.next_review_at = datetime.utcnow() + timedelta(days=INTERVAL_DAYS[0])
            if w.mastery == WrongMastery.mastered.value:
                w.mastery = WrongMastery.need_review.value
            elif w.mastery == WrongMastery.basically.value:
                w.mastery = WrongMastery.need_review.value
        else:
            db.add(WrongQuestion(
                user_id=user.id, question_id=q.id, bank_id=bank_id,
                wrong_count=1, mastery=WrongMastery.not_mastered.value,
            ))


@router.post("/sessions/{session_id}/submit", response_model=SessionOut)
def submit_session(session_id: int, data: SessionSubmitIn,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(PracticeSession).get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="练习不存在")
    if s.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该练习")
    if s.status == SessionStatus.submitted.value:
        return _session_out(db, s)

    # 批量提交剩余答案
    for ans in data.answers:
        if ans.draft_only:
            continue
        try:
            submit_answer(session_id, ans, user, db)
        except Exception:
            continue

    # 统计
    records = db.query(PracticeAnswer).filter(PracticeAnswer.session_id == s.id).all()
    correct = sum(1 for r in records if r.is_correct)
    total = s.total_questions or len(s.question_ids) or 1
    s.status = SessionStatus.submitted.value
    s.submitted_at = datetime.utcnow()
    s.correct_count = correct
    s.score = round(correct / total * 100, 1)
    db.commit()
    db.refresh(s)
    return _session_out(db, s)


@router.get("/sessions/{session_id}/result")
def session_result(session_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    s = db.query(PracticeSession).get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="练习不存在")
    if s.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问")

    records = {r.question_id: r for r in
               db.query(PracticeAnswer).filter(PracticeAnswer.session_id == s.id).all()}
    details = []
    for qid in s.question_ids:
        q = db.query(Question).get(qid)
        if not q:
            continue
        r = records.get(qid)
        payload = _question_payload(db, q, include_answer=True)
        payload["user_answer"] = json.loads(r.user_answer) if r and r.user_answer else None
        payload["is_correct"] = r.is_correct if r else None
        payload["is_ai_graded"] = r.is_ai_graded if r else False
        payload["ai_grade_note"] = r.ai_grade_note if r else ""
        payload["time_spent"] = r.time_spent if r else 0
        details.append(payload)

    answered = len(records)
    correct = sum(1 for r in records.values() if r.is_correct)
    return {
        "session": _session_out(db, s).model_dump(),
        "summary": {
            "total": s.total_questions,
            "answered": answered,
            "correct": correct,
            "wrong": answered - correct,
            "score": s.score,
            "accuracy": round(correct / answered * 100, 1) if answered else 0,
        },
        "details": details,
    }


# ---------- 错题本 ----------
@router.get("/wrong")
def list_wrong(
    bank_id: Optional[int] = None,
    mastery: Optional[str] = None,
    qtype: Optional[str] = None,
    knowledge_point: Optional[str] = None,
    sort: str = Query("wrong_count", pattern="^(wrong_count|last_wrong_at|next_review_at)$"),
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(WrongQuestion, Question).join(
        Question, WrongQuestion.question_id == Question.id
    ).filter(WrongQuestion.user_id == user.id)
    if bank_id:
        q = q.filter(WrongQuestion.bank_id == bank_id)
    if mastery:
        q = q.filter(WrongQuestion.mastery == mastery)
    if qtype:
        q = q.filter(Question.qtype == qtype)
    if knowledge_point:
        q = q.filter(Question.knowledge_points.contains(knowledge_point))

    if sort == "wrong_count":
        q = q.order_by(WrongQuestion.wrong_count.desc())
    elif sort == "last_wrong_at":
        q = q.order_by(WrongQuestion.last_wrong_at.desc())
    else:
        q = q.order_by(WrongQuestion.next_review_at.asc())

    rows = q.limit(limit).all()
    result = []
    for w, question in rows:
        bank = db.query(QuestionBank).get(w.bank_id)
        result.append({
            "id": w.id,
            "question_id": question.id,
            "bank_id": w.bank_id,
            "bank_name": bank.name if bank else "",
            "stem": question.stem,
            "qtype": question.qtype,
            "knowledge_points": question.knowledge_points or [],
            "wrong_count": w.wrong_count,
            "correct_count": w.correct_count,
            "streak": w.streak or 0,
            "mastery": w.mastery,
            "last_wrong_at": w.last_wrong_at.isoformat() if w.last_wrong_at else None,
            "next_review_at": w.next_review_at.isoformat() if w.next_review_at else None,
        })
    return {"total": len(result), "items": result}


@router.put("/wrong/{wrong_id}")
def update_wrong(wrong_id: int, data: WrongUpdateIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    w = db.query(WrongQuestion).get(wrong_id)
    if not w or w.user_id != user.id:
        raise HTTPException(status_code=404, detail="错题记录不存在")
    if data.mastery not in [m.value for m in WrongMastery]:
        raise HTTPException(status_code=400, detail="掌握度取值无效")
    w.mastery = data.mastery
    db.commit()
    return {"ok": True}


@router.delete("/wrong/{wrong_id}")
def delete_wrong(wrong_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    w = db.query(WrongQuestion).get(wrong_id)
    if not w or w.user_id != user.id:
        raise HTTPException(status_code=404, detail="错题记录不存在")
    db.delete(w)
    db.commit()
    return {"ok": True}


# ---------- 收藏 ----------
@router.post("/favorites")
def add_favorite(data: FavoriteIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    q = db.query(Question).get(data.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    bank = db.query(QuestionBank).get(q.bank_id)
    check_bank_access(db, user, bank)
    existing = db.query(Favorite).filter(
        Favorite.user_id == user.id, Favorite.question_id == data.question_id
    ).first()
    if existing:
        existing.note = data.note or existing.note
    else:
        db.add(Favorite(user_id=user.id, question_id=data.question_id,
                        bank_id=q.bank_id, note=data.note))
    db.commit()
    return {"ok": True, "message": "已收藏"}


@router.delete("/favorites/{question_id}")
def remove_favorite(question_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    f = db.query(Favorite).filter(
        Favorite.user_id == user.id, Favorite.question_id == question_id
    ).first()
    if f:
        db.delete(f)
        db.commit()
    return {"ok": True, "message": "已取消收藏"}


@router.get("/favorites")
def list_favorites(bank_id: Optional[int] = None,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    q = db.query(Favorite, Question).join(Question, Favorite.question_id == Question.id).filter(
        Favorite.user_id == user.id)
    if bank_id:
        q = q.filter(Favorite.bank_id == bank_id)
    rows = q.order_by(Favorite.created_at.desc()).all()
    return {
        "total": len(rows),
        "items": [{
            "question_id": question.id,
            "bank_id": fav.bank_id,
            "stem": question.stem,
            "qtype": question.qtype,
            "note": fav.note,
            "created_at": fav.created_at.isoformat(),
        } for fav, question in rows],
    }
