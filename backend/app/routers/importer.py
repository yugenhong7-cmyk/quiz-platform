"""智能导入路由：文本粘贴 / 文件上传 / AI 辅助 → 预览 → 确认写入。"""
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, QuestionBank, Question, QuestionOption, BlankAnswer,
    QuestionImportTask, QuestionSource, AnswerReviewStatus, ImportTaskStatus,
)
from ..schemas import (
    ImportParseIn, ImportParseOut, ParsedQuestion, ImportConfirmIn, ImportConfirmOut,
)
from ..deps import get_current_user, check_bank_access
from ..services.parser import parse_raw_text, validate_parsed
from ..services.file_import import extract_text_from_file
from ..services.dedup import content_hash, find_duplicate
from ..services import ai_client as ai

router = APIRouter(prefix="/api/import", tags=["import"])


def _to_parsed(d: dict, index: int) -> ParsedQuestion:
    return ParsedQuestion(
        index=index,
        raw_text=d.get("raw_text", ""),
        qtype=d.get("qtype", "unknown"),
        stem=d.get("stem", ""),
        options=d.get("options", []) or [],
        answer=d.get("answer", ""),
        explanation=d.get("explanation", ""),
        difficulty=d.get("difficulty", 2),
        knowledge_points=d.get("knowledge_points", []) or [],
        confidence=d.get("confidence", 0),
        uncertain_fields=d.get("uncertain_fields", []) or [],
        status=d.get("status", "ok"),
        error=d.get("error", ""),
    )


def _mark_duplicates(db: Session, bank_id: Optional[int], parsed: List[dict]) -> List[dict]:
    """标记重复题目（基于 content_hash + 相似度）。"""
    existing = []
    if bank_id:
        rows = db.query(Question.id, Question.stem, Question.qtype).filter(
            Question.bank_id == bank_id).all()
        existing = [(r[0], r[1], r[2]) for r in rows]
    seen_hashes = {}
    for p in parsed:
        h = content_hash(p.get("stem", ""), p.get("qtype", ""))
        p["_hash"] = h
        if h in seen_hashes:
            p["status"] = "duplicate"
            p["duplicate_of"] = seen_hashes[h]
            continue
        dup_id = find_duplicate(p.get("stem", ""), p.get("qtype", ""), existing)
        if dup_id:
            p["status"] = "duplicate"
            p["duplicate_of"] = dup_id
        else:
            seen_hashes[h] = None  # 占位，批内去重
    return parsed


@router.post("/parse", response_model=ImportParseOut)
def parse_text(data: ImportParseIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    if not data.raw_text or not data.raw_text.strip():
        raise HTTPException(status_code=400, detail="请输入题目文本")
    if data.bank_id:
        bank = db.query(QuestionBank).get(data.bank_id)
        if bank:
            check_bank_access(db, user, bank, need_edit=True)

    parsed = parse_raw_text(data.raw_text)
    used_ai = False
    ai_placeholder = False

    # 对 failed/unknown 的题目尝试 AI 辅助（仅在 use_ai 且已配置时）
    if data.use_ai:
        client = ai.AIClient()
        if client.is_configured:
            need = [p for p in parsed if p.get("status") in ("failed", "need_review") or p.get("qtype") == "unknown"]
            if need:
                r = ai.ai_assist_parse(client, "\n\n".join(p.get("raw_text", "") for p in need))
                if not r["is_placeholder"] and r["questions"]:
                    used_ai = True
                    # 用 AI 结果替换/补充（不允许 AI 猜测答案覆盖：只在原答案为空时填充）
                    ai_qs = r["questions"]
                    j = 0
                    for p in parsed:
                        if p.get("status") in ("failed", "need_review") and j < len(ai_qs):
                            a = ai_qs[j]
                            j += 1
                            if not p.get("stem") and a.get("stem"):
                                p["stem"] = a["stem"]
                            if not p.get("options") and a.get("options"):
                                p["options"] = a["options"]
                            if not p.get("answer") and a.get("answer") not in (None, ""):
                                p["answer"] = a["answer"]
                                p["uncertain_fields"] = list(set(p.get("uncertain_fields", []) + ["answer"]))
                            if not p.get("explanation") and a.get("explanation"):
                                p["explanation"] = a["explanation"]
                            if a.get("qtype") and p.get("qtype") == "unknown":
                                p["qtype"] = a["qtype"]
                            p["confidence"] = max(p.get("confidence", 0), 0.5)
                            ok, _ = validate_parsed(p)
                            p["status"] = "need_review" if not ok or "answer" in p.get("uncertain_fields", []) else "ok"
                elif r["is_placeholder"]:
                    ai_placeholder = True
        else:
            ai_placeholder = True

    parsed = _mark_duplicates(db, data.bank_id, parsed)

    # 统计
    total = len(parsed)
    recognized = sum(1 for p in parsed if p["status"] == "ok")
    need_review = sum(1 for p in parsed if p["status"] == "need_review")
    duplicate = sum(1 for p in parsed if p["status"] == "duplicate")
    failed = sum(1 for p in parsed if p["status"] == "failed")

    # 保存导入任务
    task = QuestionImportTask(
        user_id=user.id,
        bank_id=data.bank_id,
        source_type="ai" if used_ai else "text",
        status=ImportTaskStatus.pending_confirm.value,
        raw_content=data.raw_text,
        parsed_payload=[{k: v for k, v in p.items() if not k.startswith("_")} for p in parsed],
        stats={"total": total, "recognized": recognized, "need_review": need_review,
               "duplicate": duplicate, "failed": failed},
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return ImportParseOut(
        total=total, recognized=recognized, need_review=need_review,
        duplicate=duplicate, failed=failed,
        questions=[_to_parsed(p, i + 1) for i, p in enumerate(parsed)],
        task_id=task.id,
        used_ai=used_ai,
        ai_placeholder=ai_placeholder,
    )


@router.post("/file", response_model=ImportParseOut)
async def parse_file(
    file: UploadFile = File(...),
    bank_id: Optional[int] = None,
    use_ai: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..config import settings
    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"文件超过 {settings.MAX_UPLOAD_MB}MB 限制")

    text, err = extract_text_from_file(file.filename or "", content)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if not text.strip():
        raise HTTPException(status_code=400, detail="文件内容为空或无法提取文本")

    # 复用文本解析
    result = parse_text(ImportParseIn(raw_text=text, bank_id=bank_id, use_ai=use_ai), user, db)
    # 更新任务文件名
    if result.task_id:
        t = db.query(QuestionImportTask).get(result.task_id)
        if t:
            t.filename = file.filename or ""
            t.source_type = "file"
            db.commit()
    return result


@router.post("/confirm", response_model=ImportConfirmOut)
def confirm_import(data: ImportConfirmIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    bank = db.query(QuestionBank).get(data.bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    check_bank_access(db, user, bank, need_edit=True)

    imported = 0
    skipped_dup = 0
    skipped_invalid = 0

    existing = [(r[0], r[1], r[2]) for r in
                db.query(Question.id, Question.stem, Question.qtype).filter(Question.bank_id == bank.id).all()]
    seen_hashes = set()

    for p in data.questions:
        if p.status == "duplicate" and data.skip_duplicates:
            skipped_dup += 1
            continue
        if p.qtype == "unknown" and not data.include_unknown:
            skipped_invalid += 1
            continue
        ok, _reason = validate_parsed(p.model_dump())
        if not ok:
            skipped_invalid += 1
            continue

        h = content_hash(p.stem, p.qtype)
        if h in seen_hashes:
            skipped_dup += 1
            continue
        if data.skip_duplicates and find_duplicate(p.stem, p.qtype, existing):
            skipped_dup += 1
            continue

        q = Question(
            bank_id=bank.id,
            chapter_id=p.chapter_id if hasattr(p, "chapter_id") else None,
            qtype=p.qtype,
            stem=p.stem.strip(),
            raw_text=p.raw_text or p.stem,
            explanation=p.explanation,
            difficulty=p.difficulty or 2,
            knowledge_points=p.knowledge_points or [],
            source=QuestionSource.text_import.value,
            confidence=p.confidence,
            content_hash=h,
            review_status=(
                AnswerReviewStatus.pending.value
                if ("answer" in (p.uncertain_fields or []) or p.status == "need_review")
                else AnswerReviewStatus.confirmed.value
            ),
        )
        db.add(q)
        db.flush()

        if p.qtype in ("single", "multiple"):
            ans_letters = {str(a).upper() for a in (p.answer if isinstance(p.answer, list) else [p.answer]) if a}
            for i, opt in enumerate(p.options):
                db.add(QuestionOption(
                    question_id=q.id, label=opt.label.upper(), content=opt.content,
                    is_correct=opt.label.upper() in ans_letters, order_index=i,
                ))
        elif p.qtype == "truefalse":
            val = p.answer
            if isinstance(val, str):
                val = val in ("true", "正确", "对", "1", "T", "√")
            db.add(QuestionOption(question_id=q.id, label="T", content="正确", is_correct=bool(val), order_index=0))
            db.add(QuestionOption(question_id=q.id, label="F", content="错误", is_correct=not bool(val), order_index=1))
        elif p.qtype == "blank":
            vals = p.answer if isinstance(p.answer, list) else [p.answer]
            for i, v in enumerate(vals):
                for j, a in enumerate(str(v or "").split("|")):
                    db.add(BlankAnswer(question_id=q.id, blank_index=i, accepted=a, is_primary=(j == 0)))
        else:
            db.add(QuestionOption(question_id=q.id, label="ANS", content=str(p.answer or ""),
                                  is_correct=True, order_index=0))

        seen_hashes.add(h)
        existing.append((q.id, q.stem, q.qtype))
        imported += 1

    bank.question_count = db.query(func.count(Question.id)).filter(Question.bank_id == bank.id).scalar() or 0
    bank.updated_at = datetime.utcnow()

    # 更新任务状态
    if data.task_id:
        t = db.query(QuestionImportTask).get(data.task_id)
        if t:
            t.status = ImportTaskStatus.done.value
            t.bank_id = bank.id
            t.finished_at = datetime.utcnow()

    db.commit()
    return ImportConfirmOut(
        imported=imported, skipped_duplicate=skipped_dup,
        skipped_invalid=skipped_invalid, bank_id=bank.id,
    )


@router.get("/tasks")
def list_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tasks = db.query(QuestionImportTask).filter(
        QuestionImportTask.user_id == user.id
    ).order_by(QuestionImportTask.id.desc()).limit(20).all()
    return [{
        "id": t.id, "bank_id": t.bank_id, "source_type": t.source_type,
        "filename": t.filename, "status": t.status, "stats": t.stats,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in tasks]
