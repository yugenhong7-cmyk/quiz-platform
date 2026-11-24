"""AI 学习助手路由：解析 / 答疑 / 提示 / 相似题 / 错题分析 / 连接测试。"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Question, QuestionBank, QuestionOption, BlankAnswer,
    AIConversation, AIMessage, WrongQuestion, PracticeAnswer,
    QuestionSource, AnswerReviewStatus,
)
from ..schemas import AIChatIn, AIChatOut, AIGenerateIn, SimilarQuestionOut
from ..deps import get_current_user, check_bank_access
from ..services import ai_client as ai
from ..services.dedup import content_hash

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _load_question(db: Session, question_id: int, user: User) -> Dict[str, Any]:
    q = db.query(Question).get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    bank = db.query(QuestionBank).get(q.bank_id)
    check_bank_access(db, user, bank)
    from .questions import _extract_answer
    return {
        "id": q.id,
        "qtype": q.qtype,
        "stem": q.stem,
        "options": [{"label": o.label, "content": o.content} for o in q.options if o.label != "ANS"],
        "answer": _extract_answer(q),
        "explanation": q.explanation,
        "knowledge_points": q.knowledge_points or [],
        "bank_id": q.bank_id,
    }


@router.get("/status")
def ai_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    client = ai.get_ai_client(db)
    return {
        "configured": client.is_configured,
        "model": client.model,
        "api_base": client.api_base,
        "placeholder_note": (
            None if client.is_configured
            else "AI 服务未配置（缺少 API Key）。当前 AI 功能返回开发占位内容，不影响刷题与判题。"
        ),
    }


@router.post("/explain")
def explain(question_id: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    q = _load_question(db, question_id, user)
    client = ai.get_ai_client(db)
    r = ai.explain_question(client, q)
    return {"content": r["content"], "is_placeholder": r["is_placeholder"], "model": client.model}


@router.post("/hint")
def hint(question_id: int, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    q = _load_question(db, question_id, user)
    client = ai.get_ai_client(db)
    r = ai.hint_question(client, q)
    return {"content": r["content"], "is_placeholder": r["is_placeholder"], "model": client.model}


@router.post("/chat", response_model=AIChatOut)
def chat(data: AIChatIn, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    # 获取/创建对话
    conv = None
    if data.conversation_id:
        conv = db.query(AIConversation).get(data.conversation_id)
        if not conv or conv.user_id != user.id:
            raise HTTPException(status_code=404, detail="对话不存在")
    else:
        conv = AIConversation(
            user_id=user.id,
            title=data.message[:30] or "新对话",
            context_type=data.context_type,
            context_ref=data.context_ref,
        )
        db.add(conv)
        db.flush()

    # 载入历史
    history = []
    if data.conversation_id:
        for m in conv.messages:
            history.append({"role": m.role, "content": m.content})

    # 题目上下文
    context = None
    qid = (data.context_ref or {}).get("question_id")
    if data.context_type == "question" and qid:
        context = _load_question(db, int(qid), user)
        try:
            context["user_answer"] = json.loads(
                db.query(PracticeAnswer.user_answer).filter(
                    PracticeAnswer.user_id == user.id, PracticeAnswer.question_id == int(qid)
                ).order_by(PracticeAnswer.id.desc()).first()[0] or "null"
            )
        except Exception:
            context["user_answer"] = None

    history.append({"role": "user", "content": data.message})
    db.add(AIMessage(conversation_id=conv.id, role="user", content=data.message))

    client = ai.get_ai_client(db)
    r = ai.chat_with_context(client, history, context)
    db.add(AIMessage(conversation_id=conv.id, role="assistant",
                     content=r["content"], is_placeholder=r["is_placeholder"]))
    conv.updated_at = datetime.utcnow()
    db.commit()

    return AIChatOut(
        conversation_id=conv.id,
        reply=r["content"],
        is_placeholder=r["is_placeholder"],
        model=client.model if not r["is_placeholder"] else "placeholder",
    )


@router.get("/conversations")
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    convs = db.query(AIConversation).filter(
        AIConversation.user_id == user.id
    ).order_by(AIConversation.updated_at.desc()).limit(30).all()
    return [{
        "id": c.id, "title": c.title, "context_type": c.context_type,
        "updated_at": c.updated_at.isoformat(),
    } for c in convs]


@router.get("/conversations/{conv_id}/messages")
def conv_messages(conv_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    conv = db.query(AIConversation).get(conv_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return [{
        "id": m.id, "role": m.role, "content": m.content,
        "is_placeholder": m.is_placeholder,
        "created_at": m.created_at.isoformat(),
    } for m in conv.messages]


@router.delete("/conversations/{conv_id}")
def delete_conv(conv_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    conv = db.query(AIConversation).get(conv_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.delete(conv)
    db.commit()
    return {"ok": True}


@router.post("/generate-similar")
def generate_similar(data: AIGenerateIn, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    if not data.question_id and not data.knowledge_point:
        raise HTTPException(status_code=400, detail="请提供题目或知识点")

    source_q = {
        "stem": data.knowledge_point,
        "options": [],
        "answer": "",
        "knowledge_points": [data.knowledge_point] if data.knowledge_point else [],
    }
    if data.question_id:
        source_q = _load_question(db, data.question_id, user)

    client = ai.get_ai_client(db)
    r = ai.generate_similar_questions(client, source_q, count=data.count, qtype=data.qtype)
    if r["is_placeholder"]:
        return {
            "is_placeholder": True,
            "error": r["error"],
            "questions": [],
            "note": "AI 未配置，无法生成相似题。这是开发占位状态，不会伪造 AI 生成内容。",
        }
    if r["error"]:
        raise HTTPException(status_code=502, detail=r["error"])

    bank_id = data.bank_id or source_q.get("bank_id")
    if not bank_id:
        raise HTTPException(status_code=400, detail="请指定目标题库")

    drafts = []
    for item in r["questions"][: data.count]:
        qtype = item.get("qtype", data.qtype)
        stem = (item.get("stem") or "").strip()
        if not stem:
            continue
        q = Question(
            bank_id=bank_id,
            qtype=qtype,
            stem=stem,
            raw_text=stem,
            explanation=item.get("explanation", ""),
            difficulty=item.get("difficulty", 2),
            knowledge_points=item.get("knowledge_points", source_q.get("knowledge_points", [])),
            source=QuestionSource.ai_generated.value,
            confidence=0.7,
            content_hash=content_hash(stem, qtype),
            review_status=AnswerReviewStatus.pending.value,
            is_draft=True,   # 必须先进草稿区
        )
        db.add(q)
        db.flush()
        opts = item.get("options") or []
        if qtype in ("single", "multiple"):
            ans = item.get("answer", "")
            letters = {str(a).upper() for a in (ans if isinstance(ans, list) else [ans]) if a}
            for i, o in enumerate(opts):
                db.add(QuestionOption(
                    question_id=q.id, label=str(o.get("label", chr(65 + i))).upper(),
                    content=o.get("content", ""),
                    is_correct=str(o.get("label", chr(65 + i))).upper() in letters,
                    order_index=i,
                ))
        elif qtype == "truefalse":
            val = item.get("answer", True)
            if isinstance(val, str):
                val = val in ("true", "正确", "对", "1")
            db.add(QuestionOption(question_id=q.id, label="T", content="正确", is_correct=bool(val), order_index=0))
            db.add(QuestionOption(question_id=q.id, label="F", content="错误", is_correct=not bool(val), order_index=1))
        else:
            db.add(QuestionOption(question_id=q.id, label="ANS",
                                  content=str(item.get("answer", "")), is_correct=True, order_index=0))
        drafts.append(q.id)

    db.commit()

    from .questions import _question_out
    result = []
    for did in drafts:
        q = db.query(Question).get(did)
        result.append({"draft_id": did, "question": _question_out(q).model_dump(), "is_placeholder": False})
    return {"is_placeholder": False, "questions": result,
            "note": "AI 生成题目已进入草稿区，请审核后确认入库。"}


@router.post("/confirm-draft/{question_id}")
def confirm_draft(question_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    q = db.query(Question).get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    bank = db.query(QuestionBank).get(q.bank_id)
    check_bank_access(db, user, bank, need_edit=True)
    q.is_draft = False
    q.review_status = AnswerReviewStatus.confirmed.value
    db.commit()
    return {"ok": True, "message": "草稿已确认入库"}


@router.post("/analyze-wrong")
def analyze_wrong(bank_id: Optional[int] = None,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    q = db.query(WrongQuestion, Question).join(
        Question, WrongQuestion.question_id == Question.id
    ).filter(WrongQuestion.user_id == user.id)
    if bank_id:
        q = q.filter(WrongQuestion.bank_id == bank_id)
    rows = q.order_by(WrongQuestion.wrong_count.desc()).limit(50).all()
    wrong_list = [{
        "stem": question.stem,
        "qtype": question.qtype,
        "knowledge_points": question.knowledge_points or [],
        "wrong_count": w.wrong_count,
    } for w, question in rows]

    client = ai.get_ai_client(db)
    r = ai.analyze_wrong_questions(client, wrong_list)
    return {"content": r["content"], "is_placeholder": r["is_placeholder"],
            "wrong_count": len(wrong_list)}
