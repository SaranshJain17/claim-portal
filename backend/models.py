from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import uuid


class UserRole(str, Enum):
    PATIENT = "patient"
    HOSPITAL = "hospital"
    INSURER = "insurer"
    ADMIN = "admin"


class ClaimStatus(str, Enum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    UNDER_INVESTIGATION = "under_investigation"
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_DOCUMENTS = "pending_documents"
    PAYMENT_PROCESSING = "payment_processing"
    COMPLETED = "completed"


class NotificationType(str, Enum):
    CLAIM_SUBMITTED = "claim_submitted"
    STATUS_UPDATE = "status_update"
    DOCUMENT_REQUEST = "document_request"
    PAYMENT_PROCESSED = "payment_processed"
    SYSTEM_ALERT = "system_alert"


# Base Models
class BaseDocument(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# User Models
class UserBase(BaseModel):
    email: str
    name: str
    phone: Optional[str] = None
    role: UserRole
    is_active: bool = True

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v or '.' not in v:
            raise ValueError('Invalid email format')
        return v.lower()


class UserCreate(UserBase):
    password: str
    organization_name: Optional[str] = None  # For hospitals/insurers
    license_number: Optional[str] = None  # For hospitals
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    organization_name: Optional[str] = None
    is_active: Optional[bool] = None


class User(UserBase, BaseDocument):
    password_hash: str
    organization_name: Optional[str] = None
    license_number: Optional[str] = None
    last_login: Optional[datetime] = None
    failed_login_attempts: int = 0
    is_verified: bool = False

    class Config:
        use_enum_values = True


class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    phone: Optional[str]
    role: UserRole
    organization_name: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime


# Authentication Models
class LoginRequest(BaseModel):
    email: str
    password: str

    @validator('email')
    def validate_email(cls, v):
        return v.lower()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Claim Models
class ClaimDocumentInfo(BaseModel):
    file_name: str
    file_size: int
    file_type: str
    upload_path: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractedClaimData(BaseModel):
    patient_name: str
    patient_id: Optional[str] = None
    patient_dob: Optional[str] = None
    hospital_name: str
    doctor_name: str
    treatment_date: str
    claim_amount: float
    diagnosis: str
    treatment_type: str
    policy_number: Optional[str] = None
    procedure_codes: Optional[List[str]] = []

    @validator('claim_amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Claim amount must be greater than 0')
        return round(v, 2)


class ClaimCreate(BaseModel):
    extracted_data: ExtractedClaimData
    documents: List[ClaimDocumentInfo]
    additional_notes: Optional[str] = None
    emergency_treatment: bool = False


class ClaimStatusUpdate(BaseModel):
    status: ClaimStatus
    notes: Optional[str] = None
    updated_by_role: UserRole
    requires_documents: Optional[List[str]] = []
    estimated_processing_days: Optional[int] = None

    @validator('notes')
    def validate_notes(cls, v, values):
        status = values.get('status')
        if status in [ClaimStatus.REJECTED, ClaimStatus.PENDING_DOCUMENTS] and not v:
            raise ValueError(f'Notes are required when status is {status}')
        return v


class ClaimStatusHistory(BaseModel):
    status: ClaimStatus
    updated_by: str  # User ID
    updated_by_role: UserRole
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class Claim(BaseDocument):
    claim_number: str = Field(default_factory=lambda: f"CLM-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}")
    patient_id: str
    extracted_data: ExtractedClaimData
    documents: List[ClaimDocumentInfo]
    status: ClaimStatus = ClaimStatus.SUBMITTED
    status_history: List[ClaimStatusHistory] = []
    assigned_insurer: Optional[str] = None
    assigned_hospital: Optional[str] = None
    additional_notes: Optional[str] = None
    emergency_treatment: bool = False
    estimated_processing_days: Optional[int] = 7
    processed_amount: Optional[float] = None
    rejection_reason: Optional[str] = None

    class Config:
        use_enum_values = True


class ClaimSummary(BaseModel):
    id: str
    claim_number: str
    patient_name: str
    hospital_name: str
    claim_amount: float
    status: ClaimStatus
    created_at: datetime
    updated_at: datetime


class ClaimDetails(Claim):
    pass


# Notification Models
class NotificationCreate(BaseModel):
    recipient_id: str
    title: str
    message: str
    notification_type: NotificationType
    related_claim_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}


class Notification(BaseDocument):
    recipient_id: str
    title: str
    message: str
    notification_type: NotificationType
    related_claim_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    is_read: bool = False
    read_at: Optional[datetime] = None

    class Config:
        use_enum_values = True


# Analytics & Reporting Models
class ClaimAnalytics(BaseModel):
    total_claims: int
    claims_by_status: Dict[ClaimStatus, int]
    average_processing_time: float
    total_claim_amount: float
    approved_amount: float
    rejection_rate: float


class UserAnalytics(BaseModel):
    total_users: int
    active_users: int
    users_by_role: Dict[UserRole, int]
    new_registrations_this_month: int


# Audit Log Models
class AuditLogEntry(BaseDocument):
    user_id: str
    user_role: UserRole
    action: str
    resource_type: str
    resource_id: str
    changes: Optional[Dict[str, Any]] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    class Config:
        use_enum_values = True


# API Response Models
class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
    errors: Optional[List[str]] = None


class PaginatedResponse(BaseModel):
    success: bool = True
    data: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# File Upload Models
class FileUploadResponse(BaseModel):
    success: bool
    file_info: ClaimDocumentInfo
    extracted_data: Optional[ExtractedClaimData] = None
    message: str