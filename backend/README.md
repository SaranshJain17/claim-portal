# MediFast Health Claim Settlement Platform - Backend API

## Overview

MediFast is a comprehensive health claim settlement platform built with FastAPI, featuring secure JWT authentication, role-based access control, and a robust claim management system.

## Features

### 🔐 Authentication & Authorization
- JWT token-based authentication
- Role-based access control (Patient, Hospital, Insurer, Admin)
- Secure password hashing with bcrypt
- Token refresh mechanism
- Account lockout after failed attempts

### 👥 User Management
- Multi-role user registration
- User profile management
- Organization management for hospitals/insurers
- Account verification system

### 📋 Claim Management
- Secure claim submission with file uploads
- Mock OCR processing for document extraction
- Status workflow management
- Role-based claim updates
- Comprehensive audit logging

### 🔔 Notification System
- Real-time notifications for claim updates
- Email/SMS notification ready (mock implementation)
- In-app notification management
- Push notification support structure

### 📊 Analytics & Reporting
- Claim analytics with processing metrics
- User analytics and registration trends
- Performance monitoring
- Error tracking and reporting

### 🛡️ Security Features
- Rate limiting to prevent API abuse
- Request validation and sanitization
- Security headers for all responses
- Audit logging for compliance
- IP-based access monitoring

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/refresh` - Refresh access token

### User Management
- `GET /api/v1/users/profile` - Get current user profile
- `PUT /api/v1/users/profile` - Update user profile
- `GET /api/v1/users` - Get all users (Admin only)

### Claim Management
- `POST /api/v1/claims/upload-document` - Upload and process document
- `POST /api/v1/claims` - Submit new claim
- `GET /api/v1/claims` - Get user claims (role-based)
- `GET /api/v1/claims/{claim_id}` - Get claim details
- `PUT /api/v1/claims/{claim_id}/status` - Update claim status

### Notifications
- `GET /api/v1/notifications` - Get user notifications
- `PUT /api/v1/notifications/{notification_id}/read` - Mark as read

### Analytics
- `GET /api/v1/analytics/claims` - Claim analytics (Staff only)
- `GET /api/v1/analytics/users` - User analytics (Admin only)

### Health & Monitoring
- `GET /api/v1/health` - Health check
- `GET /api/v1/` - API information

## User Roles & Permissions

### Patient
- Submit claims
- View own claims
- Upload documents
- Receive notifications
- Update profile

### Hospital
- View assigned claims
- Update claim status (early stages)
- Provide additional documentation
- Submit claims on behalf of patients

### Insurer
- Review all claims
- Update claim status (review/approval)
- Request additional documents
- Process payments

### Admin
- Full system access
- User management
- System analytics
- Audit log access

## Database Schema

### Users Collection
```javascript
{
  id: "uuid",
  email: "string",
  name: "string",
  phone: "string?",
  role: "patient|hospital|insurer|admin",
  password_hash: "string",
  organization_name: "string?",
  license_number: "string?",
  is_active: "boolean",
  is_verified: "boolean",
  created_at: "datetime",
  updated_at: "datetime",
  last_login: "datetime?",
  failed_login_attempts: "number"
}
```

### Claims Collection
```javascript
{
  id: "uuid",
  claim_number: "string",
  patient_id: "string",
  extracted_data: {
    patient_name: "string",
    patient_id: "string",
    hospital_name: "string",
    doctor_name: "string",
    treatment_date: "string",
    claim_amount: "number",
    diagnosis: "string",
    treatment_type: "string",
    policy_number: "string?",
    procedure_codes: ["string"]
  },
  documents: [{
    file_name: "string",
    file_size: "number",
    file_type: "string",
    upload_path: "string",
    uploaded_at: "datetime"
  }],
  status: "submitted|in_review|approved|rejected|...",
  status_history: [{
    status: "string",
    updated_by: "string",
    updated_by_role: "string",
    updated_at: "datetime",
    notes: "string?"
  }],
  assigned_insurer: "string?",
  assigned_hospital: "string?",
  created_at: "datetime",
  updated_at: "datetime"
}
```

### Notifications Collection
```javascript
{
  id: "uuid",
  recipient_id: "string",
  title: "string",
  message: "string",
  notification_type: "claim_submitted|status_update|...",
  related_claim_id: "string?",
  metadata: "object",
  is_read: "boolean",
  read_at: "datetime?",
  created_at: "datetime"
}
```

## Status Workflow

Claims follow a defined workflow with role-based permissions:

```
Submitted → In Review → Under Investigation → Approved/Rejected
     ↓           ↓              ↓
Pending Documents ←────────────┘
```

### Valid Transitions
- **Submitted**: → In Review, Pending Documents, Rejected
- **In Review**: → Under Investigation, Approved, Rejected, Pending Documents
- **Under Investigation**: → Approved, Rejected, Pending Documents
- **Pending Documents**: → In Review, Rejected
- **Approved**: → Payment Processing
- **Payment Processing**: → Completed
- **Rejected/Completed**: Final states

## Security Implementation

### JWT Authentication
- Access tokens: 30 minutes expiration
- Refresh tokens: 7 days expiration
- Secure token generation with configurable secrets
- Token payload includes user ID, email, and role

### Password Security
- bcrypt hashing with automatic salting
- Minimum 8 character requirement
- Account lockout after 5 failed attempts
- Password change audit logging

### API Security
- Rate limiting: 200 requests per hour per IP
- Request size limits: 50MB maximum
- SQL injection protection
- XSS prevention headers
- CORS configuration

### Audit Logging
All sensitive operations are logged:
- User registration/login
- Claim submissions
- Status updates
- Profile changes
- Admin actions

## Environment Variables

Required environment variables:

```env
MONGO_URL="mongodb://localhost:27017"
DB_NAME="medifast_db"
CORS_ORIGINS="*"
JWT_SECRET_KEY="your-secure-secret-key"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## Installation & Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env`

3. Start the server:
```bash
python server.py
```

4. Access API documentation at: `http://localhost:8001/docs`

## Testing

### Manual Testing
Use the interactive API documentation at `/docs` to test all endpoints.

### API Testing Script
```bash
python test_api.py
```

### Example User Creation
```python
# Register a patient
POST /api/v1/auth/register
{
  "email": "patient@example.com",
  "name": "John Doe",
  "phone": "+1234567890",
  "role": "patient",
  "password": "securepassword123"
}

# Register a hospital
POST /api/v1/auth/register
{
  "email": "hospital@example.com",
  "name": "Dr. Jane Smith",
  "phone": "+1234567890",
  "role": "hospital",
  "password": "securepassword123",
  "organization_name": "City General Hospital",
  "license_number": "LIC123456"
}
```

## Error Handling

The API uses standardized error responses:

```javascript
{
  "success": false,
  "message": "Error description",
  "errors": ["Detailed error messages"]
}
```

HTTP Status Codes:
- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `422`: Validation Error
- `429`: Rate Limited
- `500`: Internal Server Error

## Monitoring & Health

### Health Check
`GET /api/v1/health` returns system status including:
- Service uptime
- Request statistics
- Error rates
- Database connectivity

### Performance Monitoring
- Request processing times
- Slow query detection
- Resource usage tracking
- Error categorization

## Future Enhancements

### Planned Features
- Real email/SMS notifications
- File storage integration (AWS S3)
- Advanced OCR with real document processing
- Payment gateway integration
- Advanced reporting and dashboards
- Mobile app API extensions
- Webhook support for third-party integrations

### Scalability Considerations
- Database connection pooling
- Redis for caching and sessions
- Microservices architecture
- API versioning strategy
- Load balancing support

## Support & Documentation

- API Documentation: `/docs` (Swagger UI)
- Alternative Docs: `/redoc` (ReDoc)
- Health Check: `/api/v1/health`
- Contact: MediFast Development Team

---

*This API is designed to be production-ready with comprehensive security, monitoring, and scalability features for healthcare claim management.*