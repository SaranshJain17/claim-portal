from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
import time
import logging
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import os
from typing import List, Optional
from contextlib import asynccontextmanager
import uvicorn

# Import models and services
from models import (
    User, UserCreate, UserUpdate, UserProfile, UserRole,
    LoginRequest, TokenResponse, RefreshTokenRequest,
    Claim, ClaimCreate, ClaimStatusUpdate, ClaimSummary,
    Notification, NotificationType,
    APIResponse, PaginatedResponse, FileUploadResponse,
    ClaimAnalytics, UserAnalytics
)
from auth import AuthService, create_auth_dependency, RoleChecker, require_admin, require_patient, require_hospital, require_insurer, require_staff, require_any_authenticated
from services import UserService, ClaimService, NotificationService, AnalyticsService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Database configuration
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'medifast_db')

# Global variables for services
db = None
auth_service = None
user_service = None
claim_service = None
notification_service = None
analytics_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global db, auth_service, user_service, claim_service, notification_service, analytics_service
    
    # Startup
    logger.info("Starting MediFast API Server...")
    
    # Initialize database connection
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Initialize services
    auth_service = AuthService(db)
    notification_service = NotificationService(db)
    user_service = UserService(db, auth_service)
    claim_service = ClaimService(db, notification_service)
    analytics_service = AnalyticsService(db)
    
    # Create indexes for better performance
    await create_database_indexes()
    
    logger.info("MediFast API Server started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down MediFast API Server...")
    client.close()


async def create_database_indexes():
    """Create database indexes for better performance"""
    try:
        # User indexes
        await db.users.create_index("email", unique=True)
        await db.users.create_index("role")
        await db.users.create_index([("email", 1), ("is_active", 1)])
        
        # Claim indexes
        await db.claims.create_index("patient_id")
        await db.claims.create_index("claim_number", unique=True)
        await db.claims.create_index("status")
        await db.claims.create_index("created_at")
        await db.claims.create_index([("patient_id", 1), ("status", 1)])
        
        # Notification indexes
        await db.notifications.create_index("recipient_id")
        await db.notifications.create_index([("recipient_id", 1), ("is_read", 1)])
        await db.notifications.create_index("created_at")
        
        # Audit log indexes
        await db.audit_logs.create_index("user_id")
        await db.audit_logs.create_index("created_at")
        await db.audit_logs.create_index([("user_id", 1), ("action", 1)])
        
        logger.info("Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"Error creating database indexes: {str(e)}")


# Initialize FastAPI app
app = FastAPI(
    title="MediFast Health Claim Settlement Platform API",
    description="Comprehensive healthcare claim management system with role-based access control",
    version="1.0.0",
    lifespan=lifespan
)

# Create API router
api_router = APIRouter(prefix="/api/v1")


# Middleware
class RequestLoggingMiddleware:
    """Custom middleware for request logging"""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            start_time = time.time()
            
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    process_time = time.time() - start_time
                    logger.info(
                        f"{scope['method']} {scope['path']} - "
                        f"Status: {message['status']} - "
                        f"Time: {process_time:.3f}s"
                    )
                await send(message)
            
            await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)


# Add middleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Global HTTP exception handler"""
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            message=exc.detail,
            errors=[exc.detail]
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unexpected errors"""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=APIResponse(
            success=False,
            message="Internal server error",
            errors=["An unexpected error occurred"]
        ).dict()
    )


# Dependency to get current user
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(create_auth_dependency(None))):
    """Dependency to get current authenticated user"""
    return await auth_service.get_current_user(credentials)


# Authentication Routes
@api_router.post("/auth/register", response_model=APIResponse)
async def register_user(user_data: UserCreate):
    """Register a new user"""
    try:
        user = await user_service.create_user(user_data)
        
        # Log audit event
        await auth_service.log_audit_event(
            user_id=user.id,
            user_role=user.role,
            action="user_register",
            resource_type="user",
            resource_id=user.id
        )
        
        return APIResponse(
            success=True,
            message="User registered successfully",
            data={"user_id": user.id, "email": user.email, "role": user.role}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed")


@api_router.post("/auth/login", response_model=TokenResponse)
async def login_user(login_data: LoginRequest):
    """User login"""
    try:
        user = await auth_service.authenticate_user(login_data.email, login_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Create tokens
        role_value = user.role.value if hasattr(user.role, 'value') else user.role
        token_data = {"sub": user.id, "email": user.email, "role": role_value}
        access_token = auth_service.create_access_token(token_data)
        refresh_token = auth_service.create_refresh_token(token_data)
        
        # Create user profile
        user_profile = UserProfile(
            id=user.id,
            email=user.email,
            name=user.name,
            phone=user.phone,
            role=user.role,
            organization_name=user.organization_name,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at
        )
        
        # Log audit event
        await auth_service.log_audit_event(
            user_id=user.id,
            user_role=user.role,
            action="user_login",
            resource_type="authentication",
            resource_id=user.id
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=1800,  # 30 minutes
            user=user_profile
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")


@api_router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(refresh_data: RefreshTokenRequest):
    """Refresh access token"""
    try:
        # Verify refresh token
        payload = auth_service.verify_token(refresh_data.refresh_token, "refresh")
        
        # Get user
        user_id = payload.get("sub")
        user = await user_service.get_user_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new tokens
        token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
        access_token = auth_service.create_access_token(token_data)
        new_refresh_token = auth_service.create_refresh_token(token_data)
        
        user_profile = await user_service.get_user_profile(user.id)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=1800,
            user=user_profile
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(status_code=500, detail="Token refresh failed")


# User Management Routes
@api_router.get("/users/profile", response_model=UserProfile)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return await user_service.get_user_profile(current_user.id)


@api_router.put("/users/profile", response_model=APIResponse)
async def update_user_profile(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update user profile"""
    try:
        await user_service.update_user(current_user.id, update_data)
        
        # Log audit event
        await auth_service.log_audit_event(
            user_id=current_user.id,
            user_role=current_user.role,
            action="profile_update",
            resource_type="user",
            resource_id=current_user.id,
            changes=update_data.dict(exclude_unset=True)
        )
        
        return APIResponse(
            success=True,
            message="Profile updated successfully"
        )
    except HTTPException:
        raise


@api_router.get("/users", response_model=List[UserProfile])
async def get_all_users(current_user: User = Depends(require_admin)):
    """Get all users (Admin only)"""
    try:
        users = await db.users.find({"is_active": True}).to_list(None)
        return [UserProfile(**{
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "phone": user.get("phone"),
            "role": user["role"],
            "organization_name": user.get("organization_name"),
            "is_active": user["is_active"],
            "is_verified": user.get("is_verified", False),
            "created_at": user["created_at"]
        }) for user in users]
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch users")


# Claim Management Routes
@api_router.post("/claims/upload-document", response_model=FileUploadResponse)
async def upload_claim_document(
    file: UploadFile = File(...),
    current_user: User = Depends(require_patient)
):
    """Upload and process claim document"""
    try:
        # Validate file type
        allowed_types = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png']
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only PDF and image files are allowed."
            )
        
        # Validate file size (10MB limit)
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="File size too large. Maximum 10MB allowed."
            )
        
        # Process with mock OCR
        extracted_data = await claim_service.process_mock_ocr(file)
        
        # Create file info
        from models import ClaimDocumentInfo
        file_info = ClaimDocumentInfo(
            file_name=file.filename,
            file_size=len(content),
            file_type=file.content_type,
            upload_path=f"/uploads/{current_user.id}/{file.filename}"
        )
        
        return FileUploadResponse(
            success=True,
            file_info=file_info,
            extracted_data=extracted_data,
            message="Document processed successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload error: {str(e)}")
        raise HTTPException(status_code=500, detail="Document processing failed")


@api_router.post("/claims", response_model=APIResponse)
async def submit_claim(
    claim_data: ClaimCreate,
    current_user: User = Depends(require_patient)
):
    """Submit a new claim"""
    try:
        claim = await claim_service.submit_claim(current_user.id, claim_data)
        
        # Log audit event
        await auth_service.log_audit_event(
            user_id=current_user.id,
            user_role=current_user.role,
            action="claim_submit",
            resource_type="claim",
            resource_id=claim.id
        )
        
        return APIResponse(
            success=True,
            message="Claim submitted successfully",
            data={
                "claim_id": claim.id,
                "claim_number": claim.claim_number,
                "status": claim.status
            }
        )
    except HTTPException:
        raise


@api_router.get("/claims", response_model=PaginatedResponse)
async def get_user_claims(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(require_any_authenticated)
):
    """Get claims based on user role"""
    try:
        if current_user.role == UserRole.PATIENT:
            result = await claim_service.get_claims_by_patient(current_user.id, page, page_size)
        else:
            # For staff roles, get all claims (simplified for MVP)
            skip = (page - 1) * page_size
            total = await db.claims.count_documents({})
            
            claims_cursor = db.claims.find({}).skip(skip).limit(page_size).sort("created_at", -1)
            claims_docs = await claims_cursor.to_list(None)
            
            claims = [ClaimSummary(**{
                "id": doc["id"],
                "claim_number": doc["claim_number"],
                "patient_name": doc["extracted_data"]["patient_name"],
                "hospital_name": doc["extracted_data"]["hospital_name"],
                "claim_amount": doc["extracted_data"]["claim_amount"],
                "status": doc["status"],
                "created_at": doc["created_at"],
                "updated_at": doc["updated_at"]
            }) for doc in claims_docs]
            
            result = {
                "claims": claims,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
        
        return PaginatedResponse(
            data=result["claims"],
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            total_pages=result["total_pages"]
        )
        
    except Exception as e:
        logger.error(f"Error fetching claims: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch claims")


@api_router.get("/claims/{claim_id}", response_model=APIResponse)
async def get_claim_details(
    claim_id: str,
    current_user: User = Depends(require_any_authenticated)
):
    """Get detailed claim information"""
    try:
        claim = await claim_service.get_claim_by_id(claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        # Check permissions
        from auth import can_view_claim
        if not can_view_claim(current_user, claim.patient_id, claim.assigned_insurer, claim.assigned_hospital):
            raise HTTPException(status_code=403, detail="Access denied")
        
        return APIResponse(
            success=True,
            message="Claim details retrieved successfully",
            data=claim.dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching claim details: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch claim details")


@api_router.put("/claims/{claim_id}/status", response_model=APIResponse)
async def update_claim_status(
    claim_id: str,
    status_update: ClaimStatusUpdate,
    current_user: User = Depends(require_staff)
):
    """Update claim status (Staff only)"""
    try:
        # Get current claim
        claim = await claim_service.get_claim_by_id(claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        # Check permissions
        from auth import can_update_claim_status
        if not can_update_claim_status(current_user, claim.status):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to update this claim's status"
            )
        
        # Update status
        status_update.updated_by_role = current_user.role
        updated_claim = await claim_service.update_claim_status(claim_id, status_update, current_user.id)
        
        # Log audit event
        await auth_service.log_audit_event(
            user_id=current_user.id,
            user_role=current_user.role,
            action="claim_status_update",
            resource_type="claim",
            resource_id=claim_id,
            changes={
                "previous_status": claim.status,
                "new_status": status_update.status,
                "notes": status_update.notes
            }
        )
        
        return APIResponse(
            success=True,
            message="Claim status updated successfully",
            data={
                "claim_id": updated_claim.id,
                "new_status": updated_claim.status,
                "updated_at": updated_claim.updated_at
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating claim status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update claim status")


# Notification Routes
@api_router.get("/notifications", response_model=PaginatedResponse)
async def get_user_notifications(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_any_authenticated)
):
    """Get user notifications"""
    try:
        result = await notification_service.get_user_notifications(current_user.id, page, page_size)
        
        return PaginatedResponse(
            data=[notif.dict() for notif in result["notifications"]],
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            total_pages=result["total_pages"]
        )
        
    except Exception as e:
        logger.error(f"Error fetching notifications: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch notifications")


@api_router.put("/notifications/{notification_id}/read", response_model=APIResponse)
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(require_any_authenticated)
):
    """Mark notification as read"""
    try:
        success = await notification_service.mark_notification_as_read(notification_id, current_user.id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        return APIResponse(
            success=True,
            message="Notification marked as read"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update notification")


# Analytics Routes
@api_router.get("/analytics/claims", response_model=ClaimAnalytics)
async def get_claim_analytics(
    days: int = 30,
    current_user: User = Depends(require_staff)
):
    """Get claim analytics (Staff only)"""
    return await analytics_service.get_claim_analytics(days)


@api_router.get("/analytics/users", response_model=UserAnalytics)
async def get_user_analytics(current_user: User = Depends(require_admin)):
    """Get user analytics (Admin only)"""
    return await analytics_service.get_user_analytics()


# Health Check Routes
@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return APIResponse(
        success=True,
        message="MediFast API is healthy",
        data={
            "status": "healthy",
            "timestamp": time.time(),
            "version": "1.0.0"
        }
    )


@api_router.get("/")
async def root():
    """Root endpoint"""
    return APIResponse(
        success=True,
        message="MediFast Health Claim Settlement Platform API v1.0.0",
        data={
            "documentation": "/docs",
            "health_check": "/api/v1/health",
            "version": "1.0.0"
        }
    )


# Include router in app
app.include_router(api_router)

# Legacy API support (for existing frontend)
legacy_router = APIRouter(prefix="/api")

@legacy_router.get("/")
async def legacy_root():
    return {"message": "MediFast Health Claim Settlement Platform API"}

@legacy_router.post("/upload-claim-document")
async def legacy_upload_document(file: UploadFile = File(...)):
    """Legacy endpoint for document upload"""
    try:
        extracted_data = await claim_service.process_mock_ocr(file)
        
        return {
            "success": True,
            "extracted_data": extracted_data.dict(),
            "file_info": {
                "filename": file.filename,
                "size": len(await file.read()),
                "content_type": file.content_type
            }
        }
    except Exception as e:
        logger.error(f"Legacy document upload error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

@legacy_router.post("/submit-claim")
async def legacy_submit_claim(claim_data: dict):
    """Legacy endpoint for claim submission"""
    try:
        # Convert legacy format to new format
        from models import ExtractedClaimData, ClaimDocumentInfo, ClaimCreate
        
        extracted_data = ExtractedClaimData(**{
            k: v for k, v in claim_data.items() 
            if k in ExtractedClaimData.__fields__
        })
        
        document_info = ClaimDocumentInfo(
            file_name=claim_data.get("file_name", "legacy_document.pdf"),
            file_size=1000,
            file_type=claim_data.get("file_type", "application/pdf"),
            upload_path="/legacy/uploads"
        )
        
        claim_create = ClaimCreate(
            extracted_data=extracted_data,
            documents=[document_info],
            additional_notes=claim_data.get("additional_notes"),
            emergency_treatment=claim_data.get("emergency_treatment", False)
        )
        
        # Create a mock patient ID for legacy support
        patient_id = "legacy-patient-" + str(hash(claim_data.get("patient_name", "anonymous")))[:8]
        
        claim = await claim_service.submit_claim(patient_id, claim_create)
        
        return claim.dict()
        
    except Exception as e:
        logger.error(f"Legacy claim submission error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error submitting claim: {str(e)}")

@legacy_router.get("/claims")
async def legacy_get_claims():
    """Legacy endpoint to get all claims"""
    try:
        claims_cursor = db.claims.find({}).sort("created_at", -1).limit(100)
        claims_docs = await claims_cursor.to_list(None)
        
        # Convert to legacy format
        legacy_claims = []
        for doc in claims_docs:
            legacy_claim = doc.copy()
            # Flatten extracted_data for legacy compatibility
            if "extracted_data" in doc:
                legacy_claim.update(doc["extracted_data"])
            legacy_claims.append(legacy_claim)
        
        return legacy_claims
        
    except Exception as e:
        logger.error(f"Legacy get claims error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error retrieving claims: {str(e)}")

app.include_router(legacy_router)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)