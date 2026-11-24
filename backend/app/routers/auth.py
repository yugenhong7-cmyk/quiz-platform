"""认证路由：注册 / 登录 / 当前用户 / 更新资料 / 用户管理（管理员）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole, LoginRecord
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut, UserUpdateIn, LoginRecordOut
from ..security import create_access_token, hash_password, verify_password
from ..deps import get_current_user, get_current_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_meta(request: Request) -> dict:
    ip = (request.client.host if request.client else "") or ""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        ip = fwd.split(",")[0].strip()
    return {"ip": ip, "user_agent": request.headers.get("user-agent", "")[:256]}


def _record_login(db: Session, *, user: User, event: str, request: Request):
    """登录数据入库：记录登录/注册/失败事件，并更新最近登录时间。"""
    meta = _client_meta(request)
    db.add(LoginRecord(
        user_id=user.id if user else None,
        username=user.username if user else meta.get("username", ""),
        event=event,
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    ))
    if user and event in ("login", "register"):
        user.last_login_at = datetime.utcnow()
    db.commit()


@router.post("/register", response_model=TokenOut)
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if data.email and db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    # 第一个注册用户成为管理员
    is_first = db.query(User).count() == 0
    user = User(
        username=data.username,
        email=data.email,
        nickname=data.nickname or data.username,
        hashed_password=hash_password(data.password),
        role=UserRole.admin.value if is_first else UserRole.user.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _record_login(db, user=user, event="register", request=request)
    token = create_access_token(user.username)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        # 失败的登录也入库，便于排查异常登录（用户名存在时关联到该用户）
        meta = _client_meta(request)
        db.add(LoginRecord(user_id=user.id if user else None, username=data.username,
                           event="failed", ip=meta["ip"], user_agent=meta["user_agent"]))
        db.commit()
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    _record_login(db, user=user, event="login", request=request)
    token = create_access_token(user.username)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/login-records", response_model=list[LoginRecordOut])
def my_login_records(limit: int = 20, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """当前用户最近的登录记录（登录数据持久化后可随时查看）。"""
    rows = (db.query(LoginRecord)
            .filter(LoginRecord.user_id == user.id)
            .order_by(LoginRecord.created_at.desc())
            .limit(max(1, min(limit, 100)))
            .all())
    return rows


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut)
def update_me(data: UserUpdateIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if data.nickname is not None:
        user.nickname = data.nickname
    if data.email is not None:
        exists = db.query(User).filter(User.email == data.email, User.id != user.id).first()
        if exists:
            raise HTTPException(status_code=400, detail="邮箱已被其他账号使用")
        user.email = data.email
    if data.password:
        if len(data.password) < 6:
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        user.hashed_password = hash_password(data.password)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.put("/users/{user_id}/toggle", response_model=UserOut)
def toggle_user(user_id: int, admin: User = Depends(get_current_admin),
                db: Session = Depends(get_db)):
    u = db.query(User).get(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    u.is_active = not u.is_active
    db.commit()
    db.refresh(u)
    return u


@router.put("/users/{user_id}/role", response_model=UserOut)
def set_role(user_id: int, role: str, admin: User = Depends(get_current_admin),
             db: Session = Depends(get_db)):
    if role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="角色无效")
    u = db.query(User).get(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    u.role = role
    db.commit()
    db.refresh(u)
    return u
