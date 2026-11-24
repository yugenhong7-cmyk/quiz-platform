"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, EmailStr


# ---------- Auth ----------
class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    email: Optional[EmailStr] = None
    nickname: Optional[str] = None


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    nickname: Optional[str] = None
    role: str
    last_login_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LoginRecordOut(BaseModel):
    id: int
    username: str
    event: str
    ip: str = ""
    user_agent: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdateIn(BaseModel):
    nickname: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None


# ---------- Bank ----------
class BankCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    category: str = "自定义"
    cover: str = ""
    visibility: str = "private"


class BankUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    cover: Optional[str] = None
    visibility: Optional[str] = None


class ChapterIn(BaseModel):
    name: str
    description: str = ""
    order_index: int = 0


class BankOut(BaseModel):
    id: int
    name: str
    description: str
    category: str
    cover: str
    visibility: str
    question_count: int
    owner_id: int
    owner_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False
    progress: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ChapterOut(BaseModel):
    id: int
    bank_id: int
    name: str
    description: str
    order_index: int
    question_count: int = 0

    class Config:
        from_attributes = True


class BankShareIn(BaseModel):
    username: str
    can_edit: bool = False


# ---------- Question ----------
class OptionIn(BaseModel):
    label: str
    content: str
    is_correct: bool = False


class QuestionIn(BaseModel):
    qtype: str = "single"
    stem: str
    options: List[OptionIn] = Field(default_factory=list)
    answer: Any = ""            # 单选 "B" / 多选 ["A","B"] / 判断 true/false / 填空 ["x"] / 简答文本
    explanation: str = ""
    difficulty: int = 2
    knowledge_points: List[str] = Field(default_factory=list)
    chapter_id: Optional[int] = None
    raw_text: str = ""
    review_status: str = "confirmed"


class QuestionUpdateIn(BaseModel):
    qtype: Optional[str] = None
    stem: Optional[str] = None
    options: Optional[List[OptionIn]] = None
    answer: Optional[Any] = None
    explanation: Optional[str] = None
    difficulty: Optional[int] = None
    knowledge_points: Optional[List[str]] = None
    chapter_id: Optional[int] = None
    review_status: Optional[str] = None


class OptionOut(BaseModel):
    id: int
    label: str
    content: str
    is_correct: bool
    order_index: int

    class Config:
        from_attributes = True


class QuestionOut(BaseModel):
    id: int
    bank_id: int
    chapter_id: Optional[int] = None
    qtype: str
    stem: str
    raw_text: str
    explanation: str
    difficulty: int
    knowledge_points: List[str] = Field(default_factory=list)
    source: str
    confidence: float
    review_status: str
    is_draft: bool
    content_hash: str = ""
    options: List[OptionOut] = Field(default_factory=list)
    answer: Any = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuestionQuery(BaseModel):
    qtype: Optional[str] = None
    chapter_id: Optional[int] = None
    keyword: Optional[str] = None
    difficulty: Optional[int] = None
    knowledge_point: Optional[str] = None
    review_status: Optional[str] = None
    is_draft: Optional[bool] = None
    page: int = 1
    page_size: int = 20


class BatchQuestionOp(BaseModel):
    ids: List[int]
    action: str   # delete / move / set_chapter / set_difficulty / dedup
    chapter_id: Optional[int] = None
    difficulty: Optional[int] = None


# ---------- Import ----------
class ImportParseIn(BaseModel):
    raw_text: str
    bank_id: Optional[int] = None
    use_ai: bool = False


class ParsedQuestion(BaseModel):
    index: int = 0
    raw_text: str = ""
    qtype: str = "unknown"
    stem: str = ""
    options: List[OptionIn] = Field(default_factory=list)
    answer: Any = ""
    explanation: str = ""
    difficulty: int = 2
    knowledge_points: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    uncertain_fields: List[str] = Field(default_factory=list)
    status: str = "ok"          # ok / need_review / duplicate / failed
    duplicate_of: Optional[int] = None
    error: str = ""
    editable: bool = True


class ImportParseOut(BaseModel):
    total: int = 0
    recognized: int = 0
    need_review: int = 0
    duplicate: int = 0
    failed: int = 0
    questions: List[ParsedQuestion] = Field(default_factory=list)
    task_id: Optional[int] = None
    used_ai: bool = False
    ai_placeholder: bool = False


class ImportConfirmIn(BaseModel):
    task_id: Optional[int] = None
    bank_id: int
    questions: List[ParsedQuestion]
    skip_duplicates: bool = True
    include_unknown: bool = False


class ImportConfirmOut(BaseModel):
    imported: int
    skipped_duplicate: int
    skipped_invalid: int
    bank_id: int


# ---------- Practice ----------
class SessionCreateIn(BaseModel):
    bank_id: int
    mode: str = "sequential"
    count: int = 10
    qtypes: List[str] = Field(default_factory=list)
    chapter_id: Optional[int] = None
    knowledge_point: Optional[str] = None
    duration_limit: Optional[int] = None   # 考试限时秒
    show_answer_mode: str = "immediate"
    # 选题策略：smart=优先未做/错题（默认）；from_start=从头按题库顺序（需用户主动选择）
    selection: str = "smart"


class SessionOut(BaseModel):
    id: int
    bank_id: int
    bank_name: str = ""
    mode: str
    status: str
    question_ids: List[int]
    answers_map: Dict[str, Any] = Field(default_factory=dict)
    show_answer_mode: str
    duration_limit: Optional[int] = None
    total_questions: int
    correct_count: int = 0
    score: Optional[float] = None
    started_at: datetime
    submitted_at: Optional[datetime] = None
    filter_meta: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class SubmitAnswerIn(BaseModel):
    question_id: int
    answer: Any
    time_spent: int = 0
    draft_only: bool = False   # 仅保存草稿不判题


class AnswerResult(BaseModel):
    question_id: int
    is_correct: Optional[bool] = None
    correct_answer: Any = None
    user_answer: Any = None
    explanation: str = ""
    ai_graded: bool = False
    grade_note: str = ""
    qtype: str = ""


class SessionSubmitIn(BaseModel):
    answers: List[SubmitAnswerIn] = Field(default_factory=list)


# ---------- Wrong / Favorite ----------
class WrongUpdateIn(BaseModel):
    mastery: str


class FavoriteIn(BaseModel):
    question_id: int
    note: str = ""


# ---------- AI ----------
class AIConfigIn(BaseModel):
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    timeout: int = 60
    max_tokens: int = 2048


class AIChatIn(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    context_type: str = "general"
    context_ref: Dict[str, Any] = Field(default_factory=dict)


class AIChatOut(BaseModel):
    conversation_id: int
    reply: str
    is_placeholder: bool = False
    model: str = ""


class AIGenerateIn(BaseModel):
    question_id: Optional[int] = None
    knowledge_point: str = ""
    count: int = 3
    qtype: str = "single"
    bank_id: Optional[int] = None


class SimilarQuestionOut(BaseModel):
    draft_id: int
    question: QuestionOut
    is_placeholder: bool = False


# ---------- Stats ----------
class StatSummary(BaseModel):
    total_answered: int
    correct_count: int
    accuracy: float
    by_type: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    by_knowledge: List[Dict[str, Any]] = Field(default_factory=list)
    daily_trend: List[Dict[str, Any]] = Field(default_factory=list)
    wrong_count: int
    wrong_by_mastery: Dict[str, int] = Field(default_factory=dict)
    favorite_count: int
    recent_sessions: List[Dict[str, Any]] = Field(default_factory=list)
    total_banks: int = 0
    total_questions: int = 0


TokenOut.model_rebuild()
