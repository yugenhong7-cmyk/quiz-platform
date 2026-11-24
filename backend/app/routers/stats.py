"""学习统计 / 系统设置路由。"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, literal
from sqlalchemy.types import Integer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, QuestionBank, Question, PracticeSession, PracticeAnswer,
    WrongQuestion, Favorite, AppSetting, WrongMastery,
)
from ..schemas import StatSummary, AIConfigIn
from ..deps import get_current_user, get_current_admin
from ..services import ai_client as ai

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats/summary", response_model=StatSummary)
def stats_summary(bank_id: Optional[int] = None,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    ans_q = db.query(PracticeAnswer).filter(PracticeAnswer.user_id == user.id)
    if bank_id:
        ans_q = ans_q.join(Question, PracticeAnswer.question_id == Question.id).filter(
            Question.bank_id == bank_id)

    total_answered = ans_q.count()
    correct = ans_q.filter(PracticeAnswer.is_correct == True).count()  # noqa: E712

    # 按题型
    by_type = {}
    type_rows = db.query(Question.qtype, func.count(PracticeAnswer.id),
                         func.sum(func.coalesce(func.cast(PracticeAnswer.is_correct, Integer()), literal(0)))
                         ).join(Question, PracticeAnswer.question_id == Question.id
                                ).filter(PracticeAnswer.user_id == user.id)
    if bank_id:
        type_rows = type_rows.filter(Question.bank_id == bank_id)
    for qtype, cnt, cor in type_rows.group_by(Question.qtype).all():
        by_type[qtype] = {
            "answered": cnt or 0,
            "correct": int(cor or 0),
            "accuracy": round((cor or 0) / cnt * 100, 1) if cnt else 0,
        }

    # 知识点掌握
    kp_stat = {}
    rows = db.query(Question.knowledge_points, PracticeAnswer.is_correct).join(
        Question, PracticeAnswer.question_id == Question.id
    ).filter(PracticeAnswer.user_id == user.id).all()
    if bank_id:
        rows = db.query(Question.knowledge_points, PracticeAnswer.is_correct).join(
            Question, PracticeAnswer.question_id == Question.id
        ).filter(PracticeAnswer.user_id == user.id, Question.bank_id == bank_id).all()
    for kps, is_cor in rows:
        for k in (kps or []):
            d = kp_stat.setdefault(k, {"answered": 0, "correct": 0})
            d["answered"] += 1
            if is_cor:
                d["correct"] += 1
    by_knowledge = sorted(
        [{"knowledge_point": k, **v, "accuracy": round(v["correct"] / v["answered"] * 100, 1)}
         for k, v in kp_stat.items() if v["answered"] > 0],
        key=lambda x: x["accuracy"],
    )

    # 每日趋势（近 30 天）
    since = datetime.utcnow() - timedelta(days=30)
    daily_rows = db.query(
        func.date(PracticeAnswer.submitted_at), func.count(PracticeAnswer.id),
        func.sum(func.coalesce(func.cast(PracticeAnswer.is_correct, Integer()), literal(0))),
    ).filter(PracticeAnswer.user_id == user.id, PracticeAnswer.submitted_at >= since)
    if bank_id:
        daily_rows = daily_rows.join(Question, PracticeAnswer.question_id == Question.id).filter(
            Question.bank_id == bank_id)
    daily_map = {str(d): {"date": str(d), "answered": c, "correct": int(cor or 0)}
                 for d, c, cor in daily_rows.group_by(func.date(PracticeAnswer.submitted_at)).all()}
    daily_trend = []
    for i in range(29, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_trend.append(daily_map.get(day, {"date": day, "answered": 0, "correct": 0}))

    # 错题
    wq = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
    if bank_id:
        wq = wq.filter(WrongQuestion.bank_id == bank_id)
    wrong_count = wq.count()
    mastery_map = {m.value: 0 for m in WrongMastery}
    for m, c in wq.with_entities(WrongQuestion.mastery, func.count(WrongQuestion.id)).group_by(WrongQuestion.mastery).all():
        mastery_map[m] = c

    # 收藏
    fav_q = db.query(Favorite).filter(Favorite.user_id == user.id)
    if bank_id:
        fav_q = fav_q.filter(Favorite.bank_id == bank_id)
    favorite_count = fav_q.count()

    # 最近练习
    sess_q = db.query(PracticeSession).filter(PracticeSession.user_id == user.id)
    if bank_id:
        sess_q = sess_q.filter(PracticeSession.bank_id == bank_id)
    recent = []
    for s in sess_q.order_by(PracticeSession.started_at.desc()).limit(10).all():
        bank = db.query(QuestionBank).get(s.bank_id)
        recent.append({
            "id": s.id, "bank_name": bank.name if bank else "", "mode": s.mode,
            "status": s.status, "score": s.score, "total": s.total_questions,
            "correct": s.correct_count,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        })

    total_banks = db.query(func.count(QuestionBank.id)).filter(QuestionBank.owner_id == user.id).scalar() or 0
    total_questions = db.query(func.count(Question.id)).join(
        QuestionBank, Question.bank_id == QuestionBank.id
    ).filter(QuestionBank.owner_id == user.id).scalar() or 0

    return StatSummary(
        total_answered=total_answered,
        correct_count=correct,
        accuracy=round(correct / total_answered * 100, 1) if total_answered else 0,
        by_type=by_type,
        by_knowledge=by_knowledge,
        daily_trend=daily_trend,
        wrong_count=wrong_count,
        wrong_by_mastery=mastery_map,
        favorite_count=favorite_count,
        recent_sessions=recent,
        total_banks=total_banks,
        total_questions=total_questions,
    )


# ---------- 系统设置 / AI 配置 ----------
SECRET_KEYS = ("ai_api_key",)


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value else default


def _set_setting(db: Session, key: str, value: str, is_secret: bool = False):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
        row.is_secret = is_secret
    else:
        db.add(AppSetting(key=key, value=value, is_secret=is_secret))


@router.get("/settings/ai")
def get_ai_config(user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from ..config import settings as env_settings
    api_key = _get_setting(db, "ai_api_key", env_settings.AI_API_KEY)
    return {
        "api_base": _get_setting(db, "ai_api_base", env_settings.AI_API_BASE),
        "model": _get_setting(db, "ai_model", env_settings.AI_MODEL),
        "timeout": int(_get_setting(db, "ai_timeout", str(env_settings.AI_TIMEOUT))),
        "max_tokens": int(_get_setting(db, "ai_max_tokens", str(env_settings.AI_MAX_TOKENS))),
        "api_key_set": bool(api_key),
        "api_key_masked": (api_key[:4] + "****" + api_key[-4:]) if len(api_key) > 8 else ("****" if api_key else ""),
    }


@router.put("/settings/ai")
def set_ai_config(data: AIConfigIn, user: User = Depends(get_current_admin),
                  db: Session = Depends(get_db)):
    _set_setting(db, "ai_api_base", data.api_base)
    _set_setting(db, "ai_model", data.model)
    _set_setting(db, "ai_timeout", str(data.timeout))
    _set_setting(db, "ai_max_tokens", str(data.max_tokens))
    if data.api_key:  # 空字符串表示不修改
        _set_setting(db, "ai_api_key", data.api_key, is_secret=True)
    db.commit()
    return {"ok": True, "message": "AI 配置已保存（API Key 安全存储在服务端）"}


@router.post("/settings/ai/test")
def test_ai_config(user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from ..config import settings as env_settings
    client = ai.AIClient(
        api_base=_get_setting(db, "ai_api_base", env_settings.AI_API_BASE),
        api_key=_get_setting(db, "ai_api_key", env_settings.AI_API_KEY),
        model=_get_setting(db, "ai_model", env_settings.AI_MODEL),
        timeout=int(_get_setting(db, "ai_timeout", str(env_settings.AI_TIMEOUT))),
        max_tokens=int(_get_setting(db, "ai_max_tokens", str(env_settings.AI_MAX_TOKENS))),
    )
    return client.test_connection()


@router.get("/settings/profile")
def get_profile(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "username": user.username, "email": user.email,
        "nickname": user.nickname, "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
