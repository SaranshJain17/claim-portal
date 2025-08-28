from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import json
import base64


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class ExtractedClaimData(BaseModel):
    patient_name: str
    patient_id: str
    hospital_name: str
    doctor_name: str
    treatment_date: str
    claim_amount: float
    diagnosis: str
    treatment_type: str

class ClaimSubmission(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_name: str
    patient_id: str
    hospital_name: str
    doctor_name: str
    treatment_date: str
    claim_amount: float
    diagnosis: str
    treatment_type: str
    file_name: str
    file_type: str
    consent_given: bool
    status: str = "Submitted"
    submission_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ClaimSubmissionCreate(BaseModel):
    patient_name: str
    patient_id: str
    hospital_name: str
    doctor_name: str
    treatment_date: str
    claim_amount: float
    diagnosis: str
    treatment_type: str
    file_name: str
    file_type: str
    consent_given: bool

class ClaimStatus(BaseModel):
    id: str
    status: str
    updated_date: datetime
    notes: Optional[str] = None

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "MediFast Health Claim Settlement Platform API"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

@api_router.post("/upload-claim-document")
async def upload_claim_document(file: UploadFile = File(...)):
    """Mock OCR processing for claim documents"""
    try:
        # Read file content
        content = await file.read()
        
        # Mock OCR extraction based on filename or random data
        mock_data_templates = [
            {
                "patient_name": "John Smith",
                "patient_id": "P123456789",
                "hospital_name": "City General Hospital",
                "doctor_name": "Dr. Sarah Johnson",
                "treatment_date": "2024-12-15",
                "claim_amount": 2500.00,
                "diagnosis": "Acute appendicitis",
                "treatment_type": "Emergency Surgery"
            },
            {
                "patient_name": "Maria Garcia",
                "patient_id": "P987654321",
                "hospital_name": "Metro Medical Center",
                "doctor_name": "Dr. Michael Chen",
                "treatment_date": "2024-12-10",
                "claim_amount": 1850.75,
                "diagnosis": "Pneumonia",
                "treatment_type": "Inpatient Treatment"
            },
            {
                "patient_name": "David Wilson",
                "patient_id": "P456789123",
                "hospital_name": "Regional Healthcare",
                "doctor_name": "Dr. Emily Davis",
                "treatment_date": "2024-12-08",
                "claim_amount": 750.50,
                "diagnosis": "Diabetes monitoring",
                "treatment_type": "Outpatient Consultation"
            }
        ]
        
        # Select random template based on file name hash
        import hashlib
        file_hash = int(hashlib.md5(file.filename.encode()).hexdigest(), 16)
        template = mock_data_templates[file_hash % len(mock_data_templates)]
        
        extracted_data = ExtractedClaimData(**template)
        
        return {
            "success": True,
            "extracted_data": extracted_data,
            "file_info": {
                "filename": file.filename,
                "size": len(content),
                "content_type": file.content_type
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

@api_router.post("/submit-claim", response_model=ClaimSubmission)
async def submit_claim(claim_data: ClaimSubmissionCreate):
    """Submit a new health insurance claim"""
    try:
        claim_dict = claim_data.dict()
        claim_obj = ClaimSubmission(**claim_dict)
        
        # Insert into database
        result = await db.claims.insert_one(claim_obj.dict())
        
        return claim_obj
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error submitting claim: {str(e)}")

@api_router.get("/claims", response_model=List[ClaimSubmission])
async def get_all_claims():
    """Get all submitted claims"""
    try:
        claims = await db.claims.find().to_list(1000)
        return [ClaimSubmission(**claim) for claim in claims]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error retrieving claims: {str(e)}")

@api_router.get("/claims/{claim_id}", response_model=ClaimSubmission)
async def get_claim(claim_id: str):
    """Get a specific claim by ID"""
    try:
        claim = await db.claims.find_one({"id": claim_id})
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        return ClaimSubmission(**claim)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error retrieving claim: {str(e)}")

@api_router.put("/claims/{claim_id}/status")
async def update_claim_status(claim_id: str, status_data: dict):
    """Update claim status (for admin/system use)"""
    try:
        valid_statuses = ["Submitted", "In Review", "Approved", "Rejected", "Pending Documents"]
        if status_data.get("status") not in valid_statuses:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        update_data = {
            "status": status_data["status"],
            "last_updated": datetime.now(timezone.utc)
        }
        
        result = await db.claims.update_one(
            {"id": claim_id}, 
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        return {"success": True, "message": "Status updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating status: {str(e)}")

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()