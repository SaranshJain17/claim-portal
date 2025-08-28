from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase
import os
from models import User, UserRole, AuditLogEntry
import logging

logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token scheme
security = HTTPBearer()


class AuthService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def verify_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Verify token type
            if payload.get("type") != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type"
                )
            
            # Check if token is expired
            if datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc) < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired"
                )
            
            return payload
        
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        try:
            user_doc = await self.db.users.find_one({"email": email.lower()})
            if not user_doc:
                return None

            user = User(**user_doc)
            
            # Check if account is locked (too many failed attempts)
            if user.failed_login_attempts >= 5:
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account locked due to too many failed login attempts. Contact support."
                )
            
            # Check if user is active
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is disabled. Contact support."
                )
            
            # Verify password
            if not self.verify_password(password, user.password_hash):
                # Increment failed login attempts
                await self.db.users.update_one(
                    {"email": email.lower()},
                    {"$inc": {"failed_login_attempts": 1}}
                )
                return None

            # Reset failed login attempts and update last login
            await self.db.users.update_one(
                {"email": email.lower()},
                {
                    "$set": {
                        "last_login": datetime.now(timezone.utc),
                        "failed_login_attempts": 0
                    }
                }
            )

            return user

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error"
            )

    async def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
        """Get current authenticated user from JWT token"""
        token = credentials.credentials
        payload = self.verify_token(token)
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

        user_doc = await self.db.users.find_one({"id": user_id})
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        user = User(**user_doc)
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled"
            )

        return user

    async def log_audit_event(
        self, 
        user_id: str, 
        user_role: UserRole, 
        action: str, 
        resource_type: str, 
        resource_id: str,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log audit events for security and compliance"""
        try:
            audit_entry = AuditLogEntry(
                user_id=user_id,
                user_role=user_role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                changes=changes or {},
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            await self.db.audit_logs.insert_one(audit_entry.dict())
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {str(e)}")


# Role-based access control decorators
class RoleChecker:
    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends()):
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(self.allowed_roles)}"
            )
        return current_user


# Common role checkers
require_admin = RoleChecker([UserRole.ADMIN])
require_patient = RoleChecker([UserRole.PATIENT])
require_hospital = RoleChecker([UserRole.HOSPITAL, UserRole.ADMIN])
require_insurer = RoleChecker([UserRole.INSURER, UserRole.ADMIN])
require_staff = RoleChecker([UserRole.HOSPITAL, UserRole.INSURER, UserRole.ADMIN])
require_any_authenticated = RoleChecker([UserRole.PATIENT, UserRole.HOSPITAL, UserRole.INSURER, UserRole.ADMIN])


# Token validation dependency
def create_auth_dependency(db: AsyncIOMotorDatabase):
    auth_service = AuthService(db)
    
    async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
        return await auth_service.get_current_user(credentials)
    
    return get_current_user


# Permission helpers
def can_view_claim(user: User, claim_patient_id: str, claim_assigned_insurer: str = None, claim_assigned_hospital: str = None) -> bool:
    """Check if user can view a specific claim"""
    if user.role == UserRole.ADMIN:
        return True
    elif user.role == UserRole.PATIENT:
        return user.id == claim_patient_id
    elif user.role == UserRole.INSURER:
        return claim_assigned_insurer == user.id
    elif user.role == UserRole.HOSPITAL:
        return claim_assigned_hospital == user.id
    return False


def can_update_claim_status(user: User, current_status: str) -> bool:
    """Check if user can update claim status based on role and current status"""
    if user.role == UserRole.ADMIN:
        return True
    elif user.role == UserRole.HOSPITAL:
        # Hospitals can update status in early stages
        return current_status in ["submitted", "pending_documents"]
    elif user.role == UserRole.INSURER:
        # Insurers can update status in review and decision stages
        return current_status in ["submitted", "in_review", "under_investigation", "pending_documents"]
    elif user.role == UserRole.PATIENT:
        # Patients can only provide additional documents
        return current_status == "pending_documents"
    return False