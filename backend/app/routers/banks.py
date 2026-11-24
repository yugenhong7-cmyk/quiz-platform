"""题库 / 章节 / 共享路由。"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, QuestionBank, Chapter, Question, BankShare,
    PracticeSession, PracticeAnswer, WrongQuestion, QuestionType,
)
from ..schemas import (
    BankCreateIn, BankUpdateIn, BankOut, ChapterIn, ChapterOut, BankShareIn,
)
from ..deps import get_current_user, get_current_admin, check_bank_access

router = APIRouter(prefix="/api/banks", tags=["banks"])


def _bank_out(db: Session, bank: QuestionBank, user: User) -> BankOut:
    owner = db.query(User).get(bank.owner_id)
    out = BankOut.model_validate(bank)
    out.owner_name = owner.username if owner else ""
    out.is_owner = bank.owner_id == user.id or user.role == "admin"
    # 学习进度：该用户在该题库的作答情况
    total = bank.question_count or 0
    answered = db.query(func.count(func.distinct(PracticeAnswer.question_id))).filter(
        PracticeAnswer.user_id == user.id,
        PracticeAnswer.question_id.in_(db.query(Question.id).filter(Question.bank_id == bank.id)),
    ).scalar() or 0
    correct = db.query(func.count(func.distinct(PracticeAnswer.question_id))).filter(
        PracticeAnswer.user_id == user.id,
        PracticeAnswer.is_correct == True,  # noqa: E712
        PracticeAnswer.question_id.in_(db.query(Question.id).filter(Question.bank_id == bank.id)),
    ).scalar() or 0
    wrong = db.query(func.count(WrongQuestion.id)).filter(
        WrongQuestion.user_id == user.id, WrongQuestion.bank_id == bank.id
    ).scalar() or 0
    out.progress = {
        "total": total,
        "answered": answered,
        "correct": correct,
        "wrong": wrong,
        "rate": round(correct / answered * 100, 1) if answered else 0,
        "percent": round(answered / total * 100, 1) if total else 0,
    }
    return out


@router.get("", response_model=list[BankOut])
def list_banks(
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    scope: str = Query("all", pattern="^(all|mine|shared|public)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(QuestionBank)
    if scope == "mine":
        q = q.filter(QuestionBank.owner_id == user.id)
    elif scope == "shared":
        shared_ids = db.query(BankShare.bank_id).filter(BankShare.user_id == user.id)
        q = q.filter(QuestionBank.id.in_(shared_ids))
    elif scope == "public":
        q = q.filter(QuestionBank.visibility == "public")
    else:
        shared_ids = db.query(BankShare.bank_id).filter(BankShare.user_id == user.id)
        q = q.filter(
            (QuestionBank.owner_id == user.id)
            | (QuestionBank.id.in_(shared_ids))
            | (QuestionBank.visibility == "public")
        )
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(QuestionBank.name.ilike(like) | QuestionBank.description.ilike(like))
    if category:
        q = q.filter(QuestionBank.category == category)
    banks = q.order_by(QuestionBank.updated_at.desc()).all()
    return [_bank_out(db, b, user) for b in banks]


@router.post("", response_model=BankOut)
def create_bank(data: BankCreateIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    bank = QuestionBank(
        name=data.name.strip(),
        description=data.description,
        category=data.category or "自定义",
        cover=data.cover or _default_cover(data.category),
        visibility=data.visibility if data.visibility in ("private", "shared", "public") else "private",
        owner_id=user.id,
    )
    db.add(bank)
    db.commit()
    db.refresh(bank)
    return _bank_out(db, bank, user)


def _default_cover(category: str) -> str:
    covers = {
        "计算机": "💻", "操作系统": "🖥️", "计算机网络": "🌐", "数据结构": "🌲",
        "人工智能": "🤖", "数学": "📐", "英语": "🔤", "考研": "📚", "公务员": "🏛️",
    }
    return covers.get(category, "📖")


@router.get("/{bank_id}", response_model=BankOut)
def get_bank(bank_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank)
    return _bank_out(db, bank, user)


@router.put("/{bank_id}", response_model=BankOut)
def update_bank(bank_id: int, data: BankUpdateIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank, need_edit=True)
    for field in ("name", "description", "category", "cover", "visibility"):
        v = getattr(data, field)
        if v is not None:
            setattr(bank, field, v)
    bank.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(bank)
    return _bank_out(db, bank, user)


@router.delete("/{bank_id}")
def delete_bank(bank_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    if bank.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="只有创建者或管理员可以删除题库")
    db.delete(bank)
    db.commit()
    return {"ok": True, "message": "题库已删除"}


@router.post("/{bank_id}/copy", response_model=BankOut)
def copy_bank(bank_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    src = db.query(QuestionBank).get(bank_id)
    if not src:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, src)
    new_bank = QuestionBank(
        name=f"{src.name} (副本)",
        description=src.description,
        category=src.category,
        cover=src.cover,
        visibility="private",
        owner_id=user.id,
    )
    db.add(new_bank)
    db.flush()
    # 复制章节
    ch_map = {}
    for ch in src.chapters:
        nch = Chapter(bank_id=new_bank.id, name=ch.name, description=ch.description,
                      order_index=ch.order_index)
        db.add(nch)
        db.flush()
        ch_map[ch.id] = nch.id
    # 复制题目
    for q in src.questions:
        nq = Question(
            bank_id=new_bank.id,
            chapter_id=ch_map.get(q.chapter_id),
            qtype=q.qtype,
            stem=q.stem,
            raw_text=q.raw_text,
            explanation=q.explanation,
            difficulty=q.difficulty,
            knowledge_points=q.knowledge_points or [],
            source=q.source,
            confidence=q.confidence,
            content_hash=q.content_hash,
            review_status=q.review_status,
        )
        db.add(nq)
        db.flush()
        for opt in q.options:
            from ..models import QuestionOption
            db.add(QuestionOption(
                question_id=nq.id, label=opt.label, content=opt.content,
                is_correct=opt.is_correct, order_index=opt.order_index,
            ))
    new_bank.question_count = len(src.questions)
    db.commit()
    db.refresh(new_bank)
    return _bank_out(db, new_bank, user)


# ---------- 章节 ----------
@router.get("/{bank_id}/chapters", response_model=list[ChapterOut])
def list_chapters(bank_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank)
    chapters = db.query(Chapter).filter(Chapter.bank_id == bank_id).order_by(Chapter.order_index).all()
    out = []
    for ch in chapters:
        c = ChapterOut.model_validate(ch)
        c.question_count = db.query(func.count(Question.id)).filter(Question.chapter_id == ch.id).scalar() or 0
        out.append(c)
    return out


@router.post("/{bank_id}/chapters", response_model=ChapterOut)
def create_chapter(bank_id: int, data: ChapterIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank, need_edit=True)
    exists = db.query(Chapter).filter(Chapter.bank_id == bank_id, Chapter.name == data.name).first()
    if exists:
        raise HTTPException(status_code=400, detail="章节名已存在")
    ch = Chapter(bank_id=bank_id, name=data.name, description=data.description,
                 order_index=data.order_index)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    c = ChapterOut.model_validate(ch)
    c.question_count = 0
    return c


@router.put("/chapters/{chapter_id}", response_model=ChapterOut)
def update_chapter(chapter_id: int, data: ChapterIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    ch = db.query(Chapter).get(chapter_id)
    if not ch:
        raise HTTPException(status_code=404, detail="章节不存在")
    bank = db.query(QuestionBank).get(ch.bank_id)
    check_bank_access(db, user, bank, need_edit=True)
    ch.name = data.name
    ch.description = data.description
    ch.order_index = data.order_index
    db.commit()
    db.refresh(ch)
    c = ChapterOut.model_validate(ch)
    c.question_count = db.query(func.count(Question.id)).filter(Question.chapter_id == ch.id).scalar() or 0
    return c


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    ch = db.query(Chapter).get(chapter_id)
    if not ch:
        raise HTTPException(status_code=404, detail="章节不存在")
    bank = db.query(QuestionBank).get(ch.bank_id)
    check_bank_access(db, user, bank, need_edit=True)
    db.query(Question).filter(Question.chapter_id == chapter_id).update({"chapter_id": None})
    db.delete(ch)
    db.commit()
    return {"ok": True}


# ---------- 共享 ----------
@router.post("/{bank_id}/share")
def share_bank(bank_id: int, data: BankShareIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    if bank.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="只有创建者可以共享题库")
    target = db.query(User).filter(User.username == data.username).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标用户不存在")
    if target.id == bank.owner_id:
        raise HTTPException(status_code=400, detail="不能共享给自己")
    existing = db.query(BankShare).filter(BankShare.bank_id == bank_id, BankShare.user_id == target.id).first()
    if existing:
        existing.can_edit = data.can_edit
    else:
        db.add(BankShare(bank_id=bank_id, user_id=target.id, can_edit=data.can_edit))
    if bank.visibility == "private":
        bank.visibility = "shared"
    db.commit()
    return {"ok": True, "message": f"已共享给 {data.username}"}


@router.get("/{bank_id}/shares")
def list_shares(bank_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    if bank.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权查看共享列表")
    shares = db.query(BankShare).filter(BankShare.bank_id == bank_id).all()
    result = []
    for s in shares:
        u = db.query(User).get(s.user_id)
        result.append({"username": u.username if u else "?", "can_edit": s.can_edit, "user_id": s.user_id})
    return result


@router.delete("/{bank_id}/share/{share_user_id}")
def remove_share(bank_id: int, share_user_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    if bank.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权管理共享")
    s = db.query(BankShare).filter(BankShare.bank_id == bank_id, BankShare.user_id == share_user_id).first()
    if s:
        db.delete(s)
        db.commit()
    return {"ok": True}


@router.get("/admin/all", response_model=list[BankOut])
def admin_list_banks(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    banks = db.query(QuestionBank).order_by(QuestionBank.updated_at.desc()).all()
    return [_bank_out(db, b, admin) for b in banks]
