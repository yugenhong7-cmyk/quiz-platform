"""数据库 ORM 模型。"""
import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey,
    Enum, UniqueConstraint, Index, JSON,
)
from sqlalchemy.orm import relationship

from .database import Base


# ---------- 枚举 ----------
class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class BankVisibility(str, enum.Enum):
    private = "private"
    shared = "shared"
    public = "public"


class QuestionType(str, enum.Enum):
    single = "single"          # 单选题
    multiple = "multiple"      # 多选题
    truefalse = "truefalse"    # 判断题
    blank = "blank"            # 填空题
    shortanswer = "shortanswer"  # 简答题
    calculation = "calculation"  # 计算题
    unknown = "unknown"        # 未识别题型


class QuestionSource(str, enum.Enum):
    manual = "manual"
    text_import = "text_import"
    file_import = "file_import"
    ai_assisted = "ai_assisted"
    ai_generated = "ai_generated"


class AnswerReviewStatus(str, enum.Enum):
    confirmed = "confirmed"       # 已确认（人工或高置信规则）
    pending = "pending"           # 答案待确认
    uncertain = "uncertain"       # 存在争议/不确定


class SessionMode(str, enum.Enum):
    sequential = "sequential"   # 顺序练习
    random = "random"           # 随机练习
    chapter = "chapter"         # 章节练习
    topic = "topic"             # 知识点练习
    specialized = "specialized" # 专项练习（按题型）
    exam = "exam"               # 模拟考试
    wrong_retry = "wrong_retry" # 错题重练
    favorite = "favorite"       # 收藏练习


class SessionStatus(str, enum.Enum):
    in_progress = "in_progress"
    submitted = "submitted"
    expired = "expired"


class WrongMastery(str, enum.Enum):
    not_mastered = "not_mastered"   # 尚未掌握
    need_review = "need_review"     # 需要复习
    basically = "basically"         # 基本掌握
    mastered = "mastered"           # 已掌握


class ImportTaskStatus(str, enum.Enum):
    parsing = "parsing"
    pending_confirm = "pending_confirm"
    importing = "importing"
    done = "done"
    failed = "failed"


# ---------- 用户 ----------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=True, index=True)
    hashed_password = Column(String(256), nullable=False)
    nickname = Column(String(64), nullable=True)
    role = Column(String(16), default=UserRole.user.value, nullable=False)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)   # 最近登录时间
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    banks = relationship("QuestionBank", back_populates="owner", cascade="all, delete-orphan")
    sessions = relationship("PracticeSession", back_populates="user", cascade="all, delete-orphan")
    wrong_questions = relationship("WrongQuestion", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    login_records = relationship("LoginRecord", back_populates="user", cascade="all, delete-orphan")


# ---------- 登录记录 ----------
class LoginRecord(Base):
    """每次登录/注册事件持久化到数据库（登录数据入库）。"""
    __tablename__ = "login_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    username = Column(String(64), nullable=False, index=True)
    event = Column(String(16), nullable=False, default="login")   # login / register / failed
    ip = Column(String(64), default="")
    user_agent = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="login_records")


# ---------- 题库 ----------
class QuestionBank(Base):
    __tablename__ = "question_banks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, index=True)
    description = Column(Text, default="")
    category = Column(String(64), default="自定义")
    cover = Column(String(256), default="")   # emoji / 颜色 / URL
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    visibility = Column(String(16), default=BankVisibility.private.value)
    question_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="banks")
    chapters = relationship("Chapter", back_populates="bank", cascade="all, delete-orphan",
                            order_by="Chapter.order_index")
    questions = relationship("Question", back_populates="bank", cascade="all, delete-orphan")
    shares = relationship("BankShare", back_populates="bank", cascade="all, delete-orphan")


class BankShare(Base):
    __tablename__ = "bank_shares"
    __table_args__ = (UniqueConstraint("bank_id", "user_id", name="uq_bank_share_user"),)

    id = Column(Integer, primary_key=True)
    bank_id = Column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    can_edit = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bank = relationship("QuestionBank", back_populates="shares")
    user = relationship("User")


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("bank_id", "name", name="uq_chapter_bank_name"),)

    id = Column(Integer, primary_key=True)
    bank_id = Column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    order_index = Column(Integer, default=0)

    bank = relationship("QuestionBank", back_populates="chapters")
    questions = relationship("Question", back_populates="chapter")


# ---------- 题目 ----------
class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    bank_id = Column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    qtype = Column(String(20), default=QuestionType.unknown.value, nullable=False, index=True)
    stem = Column(Text, nullable=False)              # 规范化题干
    raw_text = Column(Text, default="")              # 原始题目文本（便于纠错）
    explanation = Column(Text, default="")           # 解析
    difficulty = Column(Integer, default=2)          # 1 简单 2 中等 3 困难
    knowledge_points = Column(JSON, default=list)    # 知识点列表
    source = Column(String(20), default=QuestionSource.manual.value)
    confidence = Column(Float, default=1.0)          # 识别置信度 0-1
    uncertain_fields = Column(JSON, default=list)    # 不确定字段
    content_hash = Column(String(64), index=True, default="")  # 去重哈希
    review_status = Column(String(16), default=AnswerReviewStatus.confirmed.value)
    is_draft = Column(Boolean, default=False)        # AI 生成题目草稿
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bank = relationship("QuestionBank", back_populates="questions")
    chapter = relationship("Chapter", back_populates="questions")
    options = relationship("QuestionOption", back_populates="question",
                           cascade="all, delete-orphan", order_by="QuestionOption.order_index")


class QuestionOption(Base):
    __tablename__ = "question_options"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(8), nullable=False)   # A/B/C/D 或 1/2/3
    content = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    order_index = Column(Integer, default=0)

    question = relationship("Question", back_populates="options")


class BlankAnswer(Base):
    """填空题的多个标准答案 / 等价表达。"""
    __tablename__ = "blank_answers"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    blank_index = Column(Integer, default=0)      # 第几个空
    accepted = Column(Text, nullable=False)       # 标准答案或等价表达（JSON 数组序列化也可）
    is_primary = Column(Boolean, default=True)

    question = relationship("Question")


# ---------- 导入任务 ----------
class QuestionImportTask(Base):
    __tablename__ = "question_import_tasks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_id = Column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=True)
    source_type = Column(String(20), default="text")   # text / file / ai
    filename = Column(String(256), default="")
    status = Column(String(20), default=ImportTaskStatus.parsing.value)
    raw_content = Column(Text, default="")             # 原始文本
    parsed_payload = Column(JSON, default=list)        # 解析结果（待确认题目列表）
    stats = Column(JSON, default=dict)                 # {total, recognized, failed, duplicate, need_review}
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


# ---------- 练习 ----------
class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_id = Column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False, index=True)
    mode = Column(String(20), default=SessionMode.sequential.value)
    status = Column(String(20), default=SessionStatus.in_progress.value)
    question_ids = Column(JSON, default=list)     # 试卷题目 id 顺序
    answers_map = Column(JSON, default=dict)      # {question_id: answer} 草稿答案（用于断点续做）
    show_answer_mode = Column(String(20), default="immediate")  # immediate / after_submit
    duration_limit = Column(Integer, nullable=True)   # 考试限时（秒），仅 exam
    started_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    score = Column(Float, nullable=True)
    total_questions = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    filter_meta = Column(JSON, default=dict)      # 章节/题型/数量等筛选条件

    user = relationship("User", back_populates="sessions")
    bank = relationship("QuestionBank")
    answers = relationship("PracticeAnswer", back_populates="session", cascade="all, delete-orphan")


class PracticeAnswer(Base):
    __tablename__ = "practice_answers"
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_session_question"),)

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_answer = Column(Text, default="")           # JSON 序列化（选项列表 / 文本）
    correct_answer = Column(Text, default="")
    is_correct = Column(Boolean, nullable=True)      # None=未判/待人工
    is_ai_graded = Column(Boolean, default=False)    # AI 辅助评分
    ai_grade_note = Column(Text, default="")
    time_spent = Column(Integer, default=0)          # 秒
    submitted_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("PracticeSession", back_populates="answers")
    question = relationship("Question")


# ---------- 错题 ----------
class WrongQuestion(Base):
    __tablename__ = "wrong_questions"
    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_wrong_user_question"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_id = Column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False)
    wrong_count = Column(Integer, default=1)
    correct_count = Column(Integer, default=0)
    streak = Column(Integer, default=0)          # 连对次数（答错清零）
    mastery = Column(String(20), default=WrongMastery.not_mastered.value)
    last_wrong_at = Column(DateTime, default=datetime.utcnow)
    next_review_at = Column(DateTime, default=datetime.utcnow)  # 间隔复习
    review_stage = Column(Integer, default=0)      # 间隔重复阶段 0-5
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="wrong_questions")
    question = relationship("Question")
    bank = relationship("QuestionBank")


# ---------- 收藏 ----------
class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_fav_user_question"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_id = Column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="favorites")
    question = relationship("Question")


# ---------- AI ----------
class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(128), default="新对话")
    context_type = Column(String(20), default="general")  # general / question / knowledge / bank
    context_ref = Column(JSON, default=dict)               # 关联题目/知识点/题库
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    messages = relationship("AIMessage", back_populates="conversation",
                            cascade="all, delete-orphan", order_by="AIMessage.id")


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(16), nullable=False)   # user / assistant / system
    content = Column(Text, nullable=False)
    is_placeholder = Column(Boolean, default=False)  # 开发占位回答（非真实模型）
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("AIConversation", back_populates="messages")


# ---------- 系统设置（AI API 配置等，服务端保存） ----------
class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(Text, default="")
    is_secret = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Index("ix_question_bank_type", Question.bank_id, Question.qtype)
Index("ix_wrong_user_bank", WrongQuestion.user_id, WrongQuestion.bank_id)
