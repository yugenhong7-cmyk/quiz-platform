"""FastAPI 依赖注入。"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, QuestionBank, BankShare
from .security import decode_token

security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    username = decode_token(credentials.credentials)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def check_bank_access(
    db: Session,
    user: User,
    bank: QuestionBank,
    need_edit: bool = False,
) -> QuestionBank:
    """校验用户对题库的访问/编辑权限。"""
    if bank.owner_id == user.id:
        return bank
    if user.role == "admin":
        return bank
    share = db.query(BankShare).filter(
        BankShare.bank_id == bank.id, BankShare.user_id == user.id
    ).first()
    if share is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该题库")
    if need_edit and not share.can_edit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权编辑该题库（只读共享）")
    return bank
