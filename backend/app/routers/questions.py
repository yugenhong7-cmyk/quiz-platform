"""题目 CRUD 与批量操作路由。"""
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, QuestionBank, Question, QuestionOption, BlankAnswer,
    QuestionType, QuestionSource, AnswerReviewStatus,
)
from ..schemas import (
    QuestionIn, QuestionUpdateIn, QuestionOut, OptionOut, BatchQuestionOp,
)
from ..deps import get_current_user, check_bank_access
from ..services.dedup import content_hash

router = APIRouter(prefix="/api", tags=["questions"])


def _extract_answer(q: Question) -> Any:
    """从题目模型还原标准答案。"""
    if q.qtype == QuestionType.single.value:
        for o in q.options:
            if o.is_correct:
                return o.label
        return ""
    if q.qtype == QuestionType.multiple.value:
        return [o.label for o in q.options if o.is_correct]
    if q.qtype == QuestionType.truefalse.value:
        for o in q.options:
            if o.is_correct:
                return o.label == "T"
        return ""
    if q.qtype == QuestionType.blank.value:
        blanks: dict = {}
        for b in q.blank_answers if hasattr(q, "blank_answers") else []:
            blanks.setdefault(b.blank_index, []).append(b.accepted)
        if blanks:
            return [blanks[i][0] for i in sorted(blanks)]
        return []
    # 简答/计算：答案存在 explanation 前缀或单独字段——用 options 的 label="ANS"
    for o in q.options:
        if o.label == "ANS":
            return o.content
    return ""


def _question_out(q: Question) -> QuestionOut:
    out = QuestionOut.model_validate(q)
    out.options = [OptionOut.model_validate(o) for o in q.options]
    out.answer = _extract_answer(q)
    return out


def _set_answer(db: Session, q: Question, qtype: str, answer: Any):
    """写入答案到选项/BlankAnswer/ANS 选项。"""
    # 清理旧数据
    db.query(QuestionOption).filter(QuestionOption.question_id == q.id).delete()
    db.query(BlankAnswer).filter(BlankAnswer.question_id == q.id).delete()

    if qtype in ("single", "multiple"):
        letters = [answer] if isinstance(answer, str) else (answer or [])
        letters = {str(a).upper() for a in letters if a}
        # options 需要先由调用方设置（q.options 传入列表）
        # 这里只更新 is_correct —— 由调用方同步创建 options
        return letters
    if qtype == "truefalse":
        return answer
    if qtype == "blank":
        vals = answer if isinstance(answer, list) else [answer]
        for i, v in enumerate(vals):
            alts = str(v).split("|") if v is not None else [""]
            for j, a in enumerate(alts):
                db.add(BlankAnswer(question_id=q.id, blank_index=i, accepted=str(a), is_primary=(j == 0)))
        return None
    # 简答/计算：存为 ANS 选项
    db.add(QuestionOption(question_id=q.id, label="ANS", content=str(answer or ""),
                          is_correct=True, order_index=0))
    return None


@router.post("/banks/{bank_id}/questions", response_model=QuestionOut)
def create_question(bank_id: int, data: QuestionIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank, need_edit=True)

    if data.qtype not in [t.value for t in QuestionType]:
        raise HTTPException(status_code=400, detail="题型无效")

    q = Question(
        bank_id=bank_id,
        chapter_id=data.chapter_id,
        qtype=data.qtype,
        stem=data.stem.strip(),
        raw_text=data.raw_text or data.stem,
        explanation=data.explanation,
        difficulty=data.difficulty,
        knowledge_points=data.knowledge_points or [],
        source=QuestionSource.manual.value,
        confidence=1.0,
        content_hash=content_hash(data.stem, data.qtype),
        review_status=data.review_status,
    )
    db.add(q)
    db.flush()

    # 创建选项
    if data.qtype in ("single", "multiple"):
        ans_letters = {str(a).upper() for a in (data.answer if isinstance(data.answer, list) else [data.answer]) if a}
        for i, opt in enumerate(data.options):
            db.add(QuestionOption(
                question_id=q.id,
                label=opt.label.upper(),
                content=opt.content,
                is_correct=opt.label.upper() in ans_letters,
                order_index=i,
            ))
    elif data.qtype == "truefalse":
        val = data.answer
        if isinstance(val, str):
            val = val in ("true", "正确", "对", "1", "T", "√")
        db.add(QuestionOption(question_id=q.id, label="T", content="正确", is_correct=bool(val), order_index=0))
        db.add(QuestionOption(question_id=q.id, label="F", content="错误", is_correct=not bool(val), order_index=1))
    else:
        _set_answer(db, q, data.qtype, data.answer)

    bank.question_count = db.query(func.count(Question.id)).filter(Question.bank_id == bank_id).scalar() or 0
    bank.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(q)
    return _question_out(q)


@router.get("/banks/{bank_id}/questions")
def list_questions(
    bank_id: int,
    qtype: Optional[str] = None,
    chapter_id: Optional[int] = None,
    keyword: Optional[str] = None,
    difficulty: Optional[int] = None,
    knowledge_point: Optional[str] = None,
    review_status: Optional[str] = None,
    is_draft: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank)

    q = db.query(Question).filter(Question.bank_id == bank_id)
    if qtype:
        q = q.filter(Question.qtype == qtype)
    if chapter_id:
        q = q.filter(Question.chapter_id == chapter_id)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(Question.stem.ilike(like) | Question.explanation.ilike(like))
    if difficulty:
        q = q.filter(Question.difficulty == difficulty)
    if knowledge_point:
        q = q.filter(Question.knowledge_points.contains(knowledge_point))
    if review_status:
        q = q.filter(Question.review_status == review_status)
    if is_draft is not None:
        q = q.filter(Question.is_draft == is_draft)

    total = q.count()
    items = q.order_by(Question.id).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_question_out(x) for x in items],
    }


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    q = db.query(Question).get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    bank = db.query(QuestionBank).get(q.bank_id)
    check_bank_access(db, user, bank)
    return _question_out(q)


@router.put("/questions/{question_id}", response_model=QuestionOut)
def update_question(question_id: int, data: QuestionUpdateIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    q = db.query(Question).get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    bank = db.query(QuestionBank).get(q.bank_id)
    check_bank_access(db, user, bank, need_edit=True)

    if data.qtype is not None:
        q.qtype = data.qtype
    if data.stem is not None:
        q.stem = data.stem.strip()
        q.content_hash = content_hash(q.stem, q.qtype)
    if data.explanation is not None:
        q.explanation = data.explanation
    if data.difficulty is not None:
        q.difficulty = data.difficulty
    if data.knowledge_points is not None:
        q.knowledge_points = data.knowledge_points
    if data.chapter_id is not None:
        q.chapter_id = data.chapter_id
    if data.review_status is not None:
        q.review_status = data.review_status

    if data.options is not None or data.answer is not None:
        qtype = q.qtype
        if qtype in ("single", "multiple"):
            opts = data.options or []
            ans = data.answer
            ans_letters = {str(a).upper() for a in (ans if isinstance(ans, list) else [ans]) if a}
            db.query(QuestionOption).filter(QuestionOption.question_id == q.id).delete()
            for i, opt in enumerate(opts):
                db.add(QuestionOption(
                    question_id=q.id, label=opt.label.upper(), content=opt.content,
                    is_correct=opt.label.upper() in ans_letters, order_index=i,
                ))
        elif qtype == "truefalse":
            val = data.answer if data.answer is not None else None
            if val is not None:
                if isinstance(val, str):
                    val = val in ("true", "正确", "对", "1", "T", "√")
                db.query(QuestionOption).filter(QuestionOption.question_id == q.id).delete()
                db.add(QuestionOption(question_id=q.id, label="T", content="正确", is_correct=bool(val), order_index=0))
                db.add(QuestionOption(question_id=q.id, label="F", content="错误", is_correct=not bool(val), order_index=1))
        else:
            if data.answer is not None:
                _set_answer(db, q, qtype, data.answer)

    q.updated_at = datetime.utcnow()
    bank.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(q)
    return _question_out(q)


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    q = db.query(Question).get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    bank = db.query(QuestionBank).get(q.bank_id)
    check_bank_access(db, user, bank, need_edit=True)
    bank_id = q.bank_id
    db.delete(q)
    bank = db.query(QuestionBank).get(bank_id)
    bank.question_count = db.query(func.count(Question.id)).filter(Question.bank_id == bank_id).scalar() or 0
    bank.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/banks/{bank_id}/questions/batch")
def batch_op(bank_id: int, data: BatchQuestionOp, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank, need_edit=True)

    qs = db.query(Question).filter(Question.bank_id == bank_id, Question.id.in_(data.ids)).all()
    if data.action == "delete":
        for q in qs:
            db.delete(q)
        msg = f"已删除 {len(qs)} 道题"
    elif data.action == "move" or data.action == "set_chapter":
        if data.chapter_id is None:
            raise HTTPException(status_code=400, detail="缺少 chapter_id")
        for q in qs:
            q.chapter_id = data.chapter_id
        msg = f"已移动 {len(qs)} 道题"
    elif data.action == "set_difficulty":
        if data.difficulty is None:
            raise HTTPException(status_code=400, detail="缺少 difficulty")
        for q in qs:
            q.difficulty = data.difficulty
        msg = f"已更新 {len(qs)} 道题难度"
    elif data.action == "dedup":
        seen = {}
        removed = 0
        for q in db.query(Question).filter(Question.bank_id == bank_id).order_by(Question.id):
            key = q.content_hash or content_hash(q.stem, q.qtype)
            if key in seen:
                db.delete(q)
                removed += 1
            else:
                seen[key] = q.id
        msg = f"去重完成，移除 {removed} 道重复题"
    else:
        raise HTTPException(status_code=400, detail="不支持的操作")

    bank.question_count = db.query(func.count(Question.id)).filter(Question.bank_id == bank_id).scalar() or 0
    bank.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": msg, "question_count": bank.question_count}
