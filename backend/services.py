from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException, status, UploadFile
import hashlib
import os
import uuid
from models import (
    User, UserCreate, UserUpdate, UserProfile,
    Claim, ClaimCreate, ClaimStatusUpdate, ClaimSummary, ClaimDetails,
    ClaimStatus, ClaimStatusHistory, ExtractedClaimData, ClaimDocumentInfo,
    Notification, NotificationCreate, NotificationType,
    UserRole, ClaimAnalytics, UserAnalytics
)
from auth import AuthService
import json

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: AsyncIOMotorDatabase, auth_service: AuthService):
        self.db = db
        self.auth_service = auth_service

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user"""
        try:
            # Check if user already exists
            existing_user = await self.db.users.find_one({"email": user_data.email.lower()})
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email already exists"
                )

            # Create user document
            user_dict = user_data.dict(exclude={'password'})
            user_dict['email'] = user_dict['email'].lower()
            user_dict['password_hash'] = self.auth_service.hash_password(user_data.password)
            user_dict['id'] = str(uuid.uuid4())
            user_dict['created_at'] = datetime.now(timezone.utc)
            user_dict['updated_at'] = datetime.now(timezone.utc)

            user = User(**user_dict)
            
            # Insert into database
            await self.db.users.insert_one(user.dict())
            
            logger.info(f"Created new user: {user.email} with role: {user.role}")
            return user

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        try:
            user_doc = await self.db.users.find_one({"id": user_id})
            return User(**user_doc) if user_doc else None
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {str(e)}")
            return None

    async def get_user_profile(self, user_id: str) -> UserProfile:
        """Get user profile information"""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserProfile(
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

    async def update_user(self, user_id: str, update_data: UserUpdate) -> User:
        """Update user information"""
        try:
            update_dict = update_data.dict(exclude_unset=True)
            update_dict['updated_at'] = datetime.now(timezone.utc)
            
            result = await self.db.users.update_one(
                {"id": user_id},
                {"$set": update_dict}
            )
            
            if result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            return await self.get_user_by_id(user_id)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user"
            )

    async def get_users_by_role(self, role: UserRole) -> List[User]:
        """Get all users with specific role"""
        try:
            users_cursor = self.db.users.find({"role": role.value, "is_active": True})
            users_docs = await users_cursor.to_list(length=None)
            return [User(**doc) for doc in users_docs]
        except Exception as e:
            logger.error(f"Error fetching users by role {role}: {str(e)}")
            return []


class ClaimService:
    def __init__(self, db: AsyncIOMotorDatabase, notification_service: 'NotificationService'):
        self.db = db
        self.notification_service = notification_service

    async def submit_claim(self, patient_id: str, claim_data: ClaimCreate) -> Claim:
        """Submit a new claim"""
        try:
            # Create claim document
            claim_dict = claim_data.dict()
            claim_dict['patient_id'] = patient_id
            claim_dict['id'] = str(uuid.uuid4())
            claim_dict['created_at'] = datetime.now(timezone.utc)
            claim_dict['updated_at'] = datetime.now(timezone.utc)
            
            # Generate unique claim number
            claim_dict['claim_number'] = f"CLM-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
            
            # Initialize status history
            status_entry = ClaimStatusHistory(
                status=ClaimStatus.SUBMITTED,
                updated_by=patient_id,
                updated_by_role=UserRole.PATIENT,
                notes="Claim submitted by patient"
            )
            claim_dict['status_history'] = [status_entry.dict()]

            claim = Claim(**claim_dict)
            
            # Insert into database
            await self.db.claims.insert_one(claim.dict())
            
            # Send notification to patient
            await self.notification_service.create_notification(
                NotificationCreate(
                    recipient_id=patient_id,
                    title="Claim Submitted Successfully",
                    message=f"Your claim {claim.claim_number} has been submitted and is under review.",
                    notification_type=NotificationType.CLAIM_SUBMITTED,
                    related_claim_id=claim.id
                )
            )
            
            logger.info(f"Claim submitted: {claim.claim_number} by patient: {patient_id}")
            return claim

        except Exception as e:
            logger.error(f"Error submitting claim: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to submit claim"
            )

    async def get_claim_by_id(self, claim_id: str) -> Optional[Claim]:
        """Get claim by ID"""
        try:
            claim_doc = await self.db.claims.find_one({"id": claim_id})
            return Claim(**claim_doc) if claim_doc else None
        except Exception as e:
            logger.error(f"Error fetching claim {claim_id}: {str(e)}")
            return None

    async def get_claims_by_patient(self, patient_id: str, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """Get claims for a specific patient with pagination"""
        try:
            skip = (page - 1) * page_size
            
            # Get total count
            total = await self.db.claims.count_documents({"patient_id": patient_id})
            
            # Get paginated results
            claims_cursor = self.db.claims.find({"patient_id": patient_id}).skip(skip).limit(page_size).sort("created_at", -1)
            claims_docs = await claims_cursor.to_list(length=None)
            
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
            
            return {
                "claims": claims,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }

        except Exception as e:
            logger.error(f"Error fetching claims for patient {patient_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch claims"
            )

    async def update_claim_status(self, claim_id: str, status_update: ClaimStatusUpdate, updated_by: str) -> Claim:
        """Update claim status with proper workflow validation"""
        try:
            claim = await self.get_claim_by_id(claim_id)
            if not claim:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Claim not found"
                )

            # Validate status transition
            valid_transitions = self._get_valid_status_transitions(claim.status)
            if status_update.status not in valid_transitions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status transition from {claim.status} to {status_update.status}"
                )

            # Create status history entry
            status_entry = ClaimStatusHistory(
                status=status_update.status,
                updated_by=updated_by,
                updated_by_role=status_update.updated_by_role,
                notes=status_update.notes
            )

            # Update claim
            update_data = {
                "status": status_update.status.value,
                "updated_at": datetime.now(timezone.utc),
                "$push": {"status_history": status_entry.dict()}
            }

            if status_update.estimated_processing_days:
                update_data["estimated_processing_days"] = status_update.estimated_processing_days

            if status_update.status == ClaimStatus.REJECTED and status_update.notes:
                update_data["rejection_reason"] = status_update.notes

            await self.db.claims.update_one(
                {"id": claim_id},
                update_data
            )

            # Send notification to patient
            await self._send_status_update_notification(claim, status_update.status, status_update.notes)

            # Return updated claim
            return await self.get_claim_by_id(claim_id)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating claim status: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update claim status"
            )

    def _get_valid_status_transitions(self, current_status: ClaimStatus) -> List[ClaimStatus]:
        """Define valid status transitions"""
        transitions = {
            ClaimStatus.SUBMITTED: [ClaimStatus.IN_REVIEW, ClaimStatus.PENDING_DOCUMENTS, ClaimStatus.REJECTED],
            ClaimStatus.IN_REVIEW: [ClaimStatus.UNDER_INVESTIGATION, ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.PENDING_DOCUMENTS],
            ClaimStatus.UNDER_INVESTIGATION: [ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.PENDING_DOCUMENTS],
            ClaimStatus.PENDING_DOCUMENTS: [ClaimStatus.IN_REVIEW, ClaimStatus.REJECTED],
            ClaimStatus.APPROVED: [ClaimStatus.PAYMENT_PROCESSING],
            ClaimStatus.PAYMENT_PROCESSING: [ClaimStatus.COMPLETED],
            ClaimStatus.REJECTED: [],  # Final state
            ClaimStatus.COMPLETED: []  # Final state
        }
        return transitions.get(current_status, [])

    async def _send_status_update_notification(self, claim: Claim, new_status: ClaimStatus, notes: Optional[str]):
        """Send notification when claim status is updated"""
        try:
            status_messages = {
                ClaimStatus.IN_REVIEW: f"Your claim {claim.claim_number} is now under review.",
                ClaimStatus.UNDER_INVESTIGATION: f"Your claim {claim.claim_number} requires additional investigation.",
                ClaimStatus.APPROVED: f"Great news! Your claim {claim.claim_number} has been approved.",
                ClaimStatus.REJECTED: f"Your claim {claim.claim_number} has been rejected. {notes or ''}",
                ClaimStatus.PENDING_DOCUMENTS: f"Additional documents required for claim {claim.claim_number}. {notes or ''}",
                ClaimStatus.PAYMENT_PROCESSING: f"Payment is being processed for your approved claim {claim.claim_number}.",
                ClaimStatus.COMPLETED: f"Your claim {claim.claim_number} has been completed successfully."
            }

            message = status_messages.get(new_status, f"Your claim {claim.claim_number} status has been updated to {new_status.value}.")

            await self.notification_service.create_notification(
                NotificationCreate(
                    recipient_id=claim.patient_id,
                    title=f"Claim Status Update - {claim.claim_number}",
                    message=message,
                    notification_type=NotificationType.STATUS_UPDATE,
                    related_claim_id=claim.id,
                    metadata={"previous_status": claim.status, "new_status": new_status.value}
                )
            )

        except Exception as e:
            logger.error(f"Error sending status update notification: {str(e)}")

    async def process_mock_ocr(self, file: UploadFile) -> ExtractedClaimData:
        """Mock OCR processing for uploaded documents"""
        try:
            # Mock OCR templates based on file name
            templates = [
                {
                    "patient_name": "John Smith",
                    "patient_id": "P123456789",
                    "patient_dob": "1985-03-15",
                    "hospital_name": "City General Hospital",
                    "doctor_name": "Dr. Sarah Johnson",
                    "treatment_date": "2024-12-15",
                    "claim_amount": 2500.00,
                    "diagnosis": "Acute appendicitis",
                    "treatment_type": "Emergency Surgery",
                    "policy_number": "POL-789456123",
                    "procedure_codes": ["44970", "99281"]
                },
                {
                    "patient_name": "Maria Garcia",
                    "patient_id": "P987654321",
                    "patient_dob": "1978-08-22",
                    "hospital_name": "Metro Medical Center",
                    "doctor_name": "Dr. Michael Chen",
                    "treatment_date": "2024-12-10",
                    "claim_amount": 1850.75,
                    "diagnosis": "Pneumonia",
                    "treatment_type": "Inpatient Treatment",
                    "policy_number": "POL-456123789",
                    "procedure_codes": ["99223", "71020"]
                },
                {
                    "patient_name": "David Wilson",
                    "patient_id": "P456789123",
                    "patient_dob": "1965-11-05",
                    "hospital_name": "Regional Healthcare",
                    "doctor_name": "Dr. Emily Davis",
                    "treatment_date": "2024-12-08",
                    "claim_amount": 750.50,
                    "diagnosis": "Diabetes Type 2 monitoring",
                    "treatment_type": "Outpatient Consultation",
                    "policy_number": "POL-123789456",
                    "procedure_codes": ["99213", "82947"]
                }
            ]

            # Select template based on file name hash
            file_hash = int(hashlib.md5(file.filename.encode()).hexdigest(), 16)
            template = templates[file_hash % len(templates)]

            return ExtractedClaimData(**template)

        except Exception as e:
            logger.error(f"Error processing mock OCR: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process document"
            )


class NotificationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def create_notification(self, notification_data: NotificationCreate) -> Notification:
        """Create a new notification"""
        try:
            notification_dict = notification_data.dict()
            notification_dict['id'] = str(uuid.uuid4())
            notification_dict['created_at'] = datetime.now(timezone.utc)
            notification_dict['updated_at'] = datetime.now(timezone.utc)

            notification = Notification(**notification_dict)
            
            await self.db.notifications.insert_one(notification.dict())
            
            logger.info(f"Created notification for user {notification.recipient_id}: {notification.title}")
            return notification

        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create notification"
            )

    async def get_user_notifications(self, user_id: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """Get notifications for a specific user"""
        try:
            skip = (page - 1) * page_size
            
            # Get total count
            total = await self.db.notifications.count_documents({"recipient_id": user_id})
            
            # Get paginated results
            notifications_cursor = self.db.notifications.find(
                {"recipient_id": user_id}
            ).skip(skip).limit(page_size).sort("created_at", -1)
            
            notifications_docs = await notifications_cursor.to_list(length=None)
            notifications = [Notification(**doc) for doc in notifications_docs]
            
            return {
                "notifications": notifications,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
                "unread_count": await self.db.notifications.count_documents({
                    "recipient_id": user_id,
                    "is_read": False
                })
            }

        except Exception as e:
            logger.error(f"Error fetching notifications for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch notifications"
            )

    async def mark_notification_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark notification as read"""
        try:
            result = await self.db.notifications.update_one(
                {"id": notification_id, "recipient_id": user_id},
                {
                    "$set": {
                        "is_read": True,
                        "read_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            
            return result.modified_count > 0

        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            return False


class AnalyticsService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def get_claim_analytics(self, days: int = 30) -> ClaimAnalytics:
        """Get claim analytics for the specified period"""
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Aggregate claim statistics
            pipeline = [
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": None,
                    "total_claims": {"$sum": 1},
                    "total_amount": {"$sum": "$extracted_data.claim_amount"},
                    "approved_amount": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", "approved"]},
                                "$extracted_data.claim_amount",
                                0
                            ]
                        }
                    },
                    "status_counts": {
                        "$push": "$status"
                    }
                }}
            ]
            
            result = await self.db.claims.aggregate(pipeline).to_list(1)
            
            if not result:
                return ClaimAnalytics(
                    total_claims=0,
                    claims_by_status={},
                    average_processing_time=0.0,
                    total_claim_amount=0.0,
                    approved_amount=0.0,
                    rejection_rate=0.0
                )

            data = result[0]
            
            # Count claims by status
            status_counts = {}
            for status in data.get("status_counts", []):
                status_counts[status] = status_counts.get(status, 0) + 1

            # Calculate rejection rate
            rejected_count = status_counts.get("rejected", 0)
            total_claims = data["total_claims"]
            rejection_rate = (rejected_count / total_claims * 100) if total_claims > 0 else 0

            return ClaimAnalytics(
                total_claims=total_claims,
                claims_by_status=status_counts,
                average_processing_time=7.5,  # Mock average processing time
                total_claim_amount=data["total_amount"],
                approved_amount=data["approved_amount"],
                rejection_rate=rejection_rate
            )

        except Exception as e:
            logger.error(f"Error getting claim analytics: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get claim analytics"
            )

    async def get_user_analytics(self) -> UserAnalytics:
        """Get user analytics"""
        try:
            # Get total users
            total_users = await self.db.users.count_documents({})
            active_users = await self.db.users.count_documents({"is_active": True})
            
            # Get users by role
            pipeline = [
                {"$group": {"_id": "$role", "count": {"$sum": 1}}}
            ]
            
            role_counts_result = await self.db.users.aggregate(pipeline).to_list(None)
            users_by_role = {item["_id"]: item["count"] for item in role_counts_result}
            
            # New registrations this month
            start_of_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            new_registrations = await self.db.users.count_documents({
                "created_at": {"$gte": start_of_month}
            })

            return UserAnalytics(
                total_users=total_users,
                active_users=active_users,
                users_by_role=users_by_role,
                new_registrations_this_month=new_registrations
            )

        except Exception as e:
            logger.error(f"Error getting user analytics: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get user analytics"
            )