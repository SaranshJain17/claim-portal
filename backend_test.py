import requests
import sys
import json
import io
import time
from datetime import datetime
from typing import Dict, Any, Optional

class MediFastAPITester:
    def __init__(self, base_url="https://claim-portal-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.v1_api = f"{base_url}/api/v1"
        self.legacy_api = f"{base_url}/api"
        
        # Test data storage
        self.tokens = {}
        self.users = {}
        self.claims = {}
        self.notifications = {}
        
        # Test counters
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test results"""
        self.tests_run += 1
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"    {details}")
        
        if success:
            self.tests_passed += 1
        else:
            self.failed_tests.append(f"{name}: {details}")

    def make_request(self, method: str, url: str, headers: Dict = None, data: Any = None, files: Any = None) -> tuple:
        """Make HTTP request and return (success, response_data, status_code)"""
        try:
            default_headers = {'Content-Type': 'application/json'}
            if headers:
                default_headers.update(headers)
            
            # Remove Content-Type for file uploads
            if files:
                default_headers.pop('Content-Type', None)
            
            kwargs = {'headers': default_headers}
            if data and not files:
                kwargs['json'] = data
            elif data and files:
                kwargs['data'] = data
            if files:
                kwargs['files'] = files

            if method.upper() == 'GET':
                response = requests.get(url, **kwargs)
            elif method.upper() == 'POST':
                response = requests.post(url, **kwargs)
            elif method.upper() == 'PUT':
                response = requests.put(url, **kwargs)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, **kwargs)
            else:
                return False, {"error": "Unsupported method"}, 400

            try:
                response_data = response.json()
            except:
                response_data = {"raw_response": response.text}

            return response.status_code < 400, response_data, response.status_code

        except Exception as e:
            return False, {"error": str(e)}, 0

    def test_health_check(self):
        """Test health check endpoint"""
        print("\n🔍 Testing Health Check...")
        
        success, data, status = self.make_request('GET', f"{self.v1_api}/health")
        self.log_test(
            "Health Check", 
            success and status == 200,
            f"Status: {status}, Response: {data.get('message', 'No message')}"
        )

    def test_user_registration(self):
        """Test user registration for different roles"""
        print("\n🔍 Testing User Registration...")
        
        test_users = [
            {
                "role": "patient",
                "email": f"patient_{int(time.time())}@test.com",
                "password": "TestPass123!",
                "name": "Test Patient",
                "phone": "+1234567890"
            },
            {
                "role": "hospital",
                "email": f"hospital_{int(time.time())}@test.com",
                "password": "TestPass123!",
                "name": "Test Hospital",
                "organization_name": "Test Medical Center",
                "license_number": "LIC123456"
            },
            {
                "role": "insurer",
                "email": f"insurer_{int(time.time())}@test.com",
                "password": "TestPass123!",
                "name": "Test Insurer",
                "organization_name": "Test Insurance Co"
            },
            {
                "role": "admin",
                "email": f"admin_{int(time.time())}@test.com",
                "password": "TestPass123!",
                "name": "Test Admin"
            }
        ]

        for user_data in test_users:
            success, data, status = self.make_request('POST', f"{self.v1_api}/auth/register", data=user_data)
            
            if success and status == 200:
                self.users[user_data["role"]] = {
                    "email": user_data["email"],
                    "password": user_data["password"],
                    "user_id": data.get("data", {}).get("user_id")
                }
            
            self.log_test(
                f"Register {user_data['role']} user",
                success and status == 200,
                f"Status: {status}, Email: {user_data['email']}"
            )

    def test_user_authentication(self):
        """Test user login for all registered users"""
        print("\n🔍 Testing User Authentication...")
        
        for role, user_info in self.users.items():
            login_data = {
                "email": user_info["email"],
                "password": user_info["password"]
            }
            
            success, data, status = self.make_request('POST', f"{self.v1_api}/auth/login", data=login_data)
            
            if success and status == 200:
                self.tokens[role] = {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "user": data.get("user")
                }
            
            self.log_test(
                f"Login {role} user",
                success and status == 200,
                f"Status: {status}, Token received: {bool(data.get('access_token'))}"
            )

    def test_token_refresh(self):
        """Test token refresh functionality"""
        print("\n🔍 Testing Token Refresh...")
        
        if "patient" in self.tokens:
            refresh_data = {
                "refresh_token": self.tokens["patient"]["refresh_token"]
            }
            
            success, data, status = self.make_request('POST', f"{self.v1_api}/auth/refresh", data=refresh_data)
            
            if success and status == 200:
                # Update token
                self.tokens["patient"]["access_token"] = data.get("access_token")
                self.tokens["patient"]["refresh_token"] = data.get("refresh_token")
            
            self.log_test(
                "Token refresh",
                success and status == 200,
                f"Status: {status}, New token received: {bool(data.get('access_token'))}"
            )

    def test_user_profile_operations(self):
        """Test user profile get and update operations"""
        print("\n🔍 Testing User Profile Operations...")
        
        for role in ["patient", "hospital", "insurer", "admin"]:
            if role not in self.tokens:
                continue
                
            headers = {"Authorization": f"Bearer {self.tokens[role]['access_token']}"}
            
            # Test get profile
            success, data, status = self.make_request('GET', f"{self.v1_api}/users/profile", headers=headers)
            self.log_test(
                f"Get {role} profile",
                success and status == 200,
                f"Status: {status}, Profile: {data.get('name', 'No name')}"
            )
            
            # Test update profile
            update_data = {"name": f"Updated {role.title()} Name"}
            success, data, status = self.make_request('PUT', f"{self.v1_api}/users/profile", headers=headers, data=update_data)
            self.log_test(
                f"Update {role} profile",
                success and status == 200,
                f"Status: {status}, Success: {data.get('success', False)}"
            )

    def test_admin_user_list(self):
        """Test admin-only user list endpoint"""
        print("\n🔍 Testing Admin User List...")
        
        if "admin" in self.tokens:
            headers = {"Authorization": f"Bearer {self.tokens['admin']['access_token']}"}
            success, data, status = self.make_request('GET', f"{self.v1_api}/users", headers=headers)
            
            self.log_test(
                "Admin get all users",
                success and status == 200,
                f"Status: {status}, Users count: {len(data) if isinstance(data, list) else 0}"
            )
        
        # Test unauthorized access
        if "patient" in self.tokens:
            headers = {"Authorization": f"Bearer {self.tokens['patient']['access_token']}"}
            success, data, status = self.make_request('GET', f"{self.v1_api}/users", headers=headers)
            
            self.log_test(
                "Patient unauthorized user list access",
                not success and status == 403,
                f"Status: {status} (should be 403)"
            )

    def test_document_upload(self):
        """Test document upload with OCR processing"""
        print("\n🔍 Testing Document Upload...")
        
        if "patient" not in self.tokens:
            self.log_test("Document upload", False, "No patient token available")
            return
        
        headers = {"Authorization": f"Bearer {self.tokens['patient']['access_token']}"}
        
        # Create a mock PDF file
        mock_file_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        files = {'file': ('test_medical_bill.pdf', io.BytesIO(mock_file_content), 'application/pdf')}
        
        success, data, status = self.make_request(
            'POST', 
            f"{self.v1_api}/claims/upload-document", 
            headers={"Authorization": f"Bearer {self.tokens['patient']['access_token']}"}, 
            files=files
        )
        
        if success and status == 200:
            self.extracted_data = data.get("extracted_data")
        
        self.log_test(
            "Document upload and OCR",
            success and status == 200,
            f"Status: {status}, Extracted data: {bool(data.get('extracted_data'))}"
        )

    def test_claim_submission(self):
        """Test claim submission"""
        print("\n🔍 Testing Claim Submission...")
        
        if "patient" not in self.tokens:
            self.log_test("Claim submission", False, "No patient token available")
            return
        
        headers = {"Authorization": f"Bearer {self.tokens['patient']['access_token']}"}
        
        # Mock claim data
        claim_data = {
            "extracted_data": {
                "patient_name": "John Doe",
                "patient_id": "P123456",
                "hospital_name": "Test Hospital",
                "doctor_name": "Dr. Smith",
                "treatment_date": "2024-12-15",
                "claim_amount": 1500.00,
                "diagnosis": "Test diagnosis",
                "treatment_type": "Outpatient"
            },
            "documents": [{
                "file_name": "test_bill.pdf",
                "file_size": 1024,
                "file_type": "application/pdf",
                "upload_path": "/test/path"
            }],
            "additional_notes": "Test claim submission",
            "emergency_treatment": False
        }
        
        success, data, status = self.make_request('POST', f"{self.v1_api}/claims", headers=headers, data=claim_data)
        
        if success and status == 200:
            self.claims["test_claim"] = {
                "claim_id": data.get("data", {}).get("claim_id"),
                "claim_number": data.get("data", {}).get("claim_number")
            }
        
        self.log_test(
            "Claim submission",
            success and status == 200,
            f"Status: {status}, Claim ID: {data.get('data', {}).get('claim_id', 'None')}"
        )

    def test_claim_retrieval(self):
        """Test claim retrieval operations"""
        print("\n🔍 Testing Claim Retrieval...")
        
        # Test get claims for patient
        if "patient" in self.tokens:
            headers = {"Authorization": f"Bearer {self.tokens['patient']['access_token']}"}
            success, data, status = self.make_request('GET', f"{self.v1_api}/claims", headers=headers)
            
            self.log_test(
                "Get patient claims",
                success and status == 200,
                f"Status: {status}, Claims count: {len(data.get('data', []))}"
            )
        
        # Test get claims for staff (hospital/insurer)
        for role in ["hospital", "insurer"]:
            if role in self.tokens:
                headers = {"Authorization": f"Bearer {self.tokens[role]['access_token']}"}
                success, data, status = self.make_request('GET', f"{self.v1_api}/claims", headers=headers)
                
                self.log_test(
                    f"Get {role} claims",
                    success and status == 200,
                    f"Status: {status}, Claims count: {len(data.get('data', []))}"
                )

    def test_claim_details(self):
        """Test detailed claim retrieval"""
        print("\n🔍 Testing Claim Details...")
        
        if "test_claim" not in self.claims or "patient" not in self.tokens:
            self.log_test("Claim details", False, "No test claim or patient token available")
            return
        
        claim_id = self.claims["test_claim"]["claim_id"]
        headers = {"Authorization": f"Bearer {self.tokens['patient']['access_token']}"}
        
        success, data, status = self.make_request('GET', f"{self.v1_api}/claims/{claim_id}", headers=headers)
        
        self.log_test(
            "Get claim details",
            success and status == 200,
            f"Status: {status}, Claim found: {bool(data.get('data'))}"
        )

    def test_claim_status_update(self):
        """Test claim status updates by different roles"""
        print("\n🔍 Testing Claim Status Updates...")
        
        if "test_claim" not in self.claims:
            self.log_test("Claim status update", False, "No test claim available")
            return
        
        claim_id = self.claims["test_claim"]["claim_id"]
        
        # Test hospital updating status
        if "hospital" in self.tokens:
            headers = {"Authorization": f"Bearer {self.tokens['hospital']['access_token']}"}
            update_data = {
                "status": "in_review",
                "notes": "Claim under hospital review",
                "updated_by_role": "hospital"
            }
            
            success, data, status = self.make_request('PUT', f"{self.v1_api}/claims/{claim_id}/status", headers=headers, data=update_data)
            
            self.log_test(
                "Hospital update claim status",
                success and status == 200,
                f"Status: {status}, Updated: {data.get('success', False)}"
            )
        
        # Test insurer updating status
        if "insurer" in self.tokens:
            headers = {"Authorization": f"Bearer {self.tokens['insurer']['access_token']}"}
            update_data = {
                "status": "approved",
                "notes": "Claim approved by insurer",
                "updated_by_role": "insurer"
            }
            
            success, data, status = self.make_request('PUT', f"{self.v1_api}/claims/{claim_id}/status", headers=headers, data=update_data)
            
            self.log_test(
                "Insurer update claim status",
                success and status == 200,
                f"Status: {status}, Updated: {data.get('success', False)}"
            )

    def test_notifications(self):
        """Test notification system"""
        print("\n🔍 Testing Notifications...")
        
        if "patient" not in self.tokens:
            self.log_test("Get notifications", False, "No patient token available")
            return
        
        headers = {"Authorization": f"Bearer {self.tokens['patient']['access_token']}"}
        
        # Get notifications
        success, data, status = self.make_request('GET', f"{self.v1_api}/notifications", headers=headers)
        
        notifications = data.get('data', [])
        self.log_test(
            "Get user notifications",
            success and status == 200,
            f"Status: {status}, Notifications count: {len(notifications)}"
        )
        
        # Mark first notification as read if available
        if notifications and len(notifications) > 0:
            notification_id = notifications[0].get('id')
            if notification_id:
                success, data, status = self.make_request('PUT', f"{self.v1_api}/notifications/{notification_id}/read", headers=headers)
                
                self.log_test(
                    "Mark notification as read",
                    success and status == 200,
                    f"Status: {status}, Marked as read: {data.get('success', False)}"
                )

    def test_analytics(self):
        """Test analytics endpoints"""
        print("\n🔍 Testing Analytics...")
        
        # Test claim analytics (staff only)
        for role in ["hospital", "insurer", "admin"]:
            if role in self.tokens:
                headers = {"Authorization": f"Bearer {self.tokens[role]['access_token']}"}
                success, data, status = self.make_request('GET', f"{self.v1_api}/analytics/claims", headers=headers)
                
                self.log_test(
                    f"{role.title()} claim analytics",
                    success and status == 200,
                    f"Status: {status}, Total claims: {data.get('total_claims', 0)}"
                )
                break
        
        # Test user analytics (admin only)
        if "admin" in self.tokens:
            headers = {"Authorization": f"Bearer {self.tokens['admin']['access_token']}"}
            success, data, status = self.make_request('GET', f"{self.v1_api}/analytics/users", headers=headers)
            
            self.log_test(
                "Admin user analytics",
                success and status == 200,
                f"Status: {status}, Total users: {data.get('total_users', 0)}"
            )

    def test_legacy_endpoints(self):
        """Test legacy API compatibility"""
        print("\n🔍 Testing Legacy API Endpoints...")
        
        # Test legacy document upload
        mock_file_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        files = {'file': ('legacy_test.pdf', io.BytesIO(mock_file_content), 'application/pdf')}
        
        success, data, status = self.make_request('POST', f"{self.legacy_api}/upload-claim-document", files=files)
        
        self.log_test(
            "Legacy document upload",
            success and status == 200,
            f"Status: {status}, Success: {data.get('success', False)}"
        )
        
        # Test legacy claim submission
        legacy_claim_data = {
            "patient_name": "Legacy Patient",
            "hospital_name": "Legacy Hospital",
            "doctor_name": "Dr. Legacy",
            "treatment_date": "2024-12-15",
            "claim_amount": 1000.00,
            "diagnosis": "Legacy diagnosis",
            "treatment_type": "Legacy treatment"
        }
        
        success, data, status = self.make_request('POST', f"{self.legacy_api}/submit-claim", data=legacy_claim_data)
        
        self.log_test(
            "Legacy claim submission",
            success and status == 200,
            f"Status: {status}, Claim ID: {data.get('id', 'None')}"
        )
        
        # Test legacy get claims
        success, data, status = self.make_request('GET', f"{self.legacy_api}/claims")
        
        self.log_test(
            "Legacy get claims",
            success and status == 200,
            f"Status: {status}, Claims count: {len(data) if isinstance(data, list) else 0}"
        )

    def test_security_features(self):
        """Test security features"""
        print("\n🔍 Testing Security Features...")
        
        # Test invalid token
        invalid_headers = {"Authorization": "Bearer invalid_token_12345"}
        success, data, status = self.make_request('GET', f"{self.v1_api}/users/profile", headers=invalid_headers)
        
        self.log_test(
            "Invalid token rejection",
            not success and status == 401,
            f"Status: {status} (should be 401)"
        )
        
        # Test missing token
        success, data, status = self.make_request('GET', f"{self.v1_api}/users/profile")
        
        self.log_test(
            "Missing token rejection",
            not success and status in [401, 422],
            f"Status: {status} (should be 401 or 422)"
        )
        
        # Test role-based access control
        if "patient" in self.tokens and "admin" in self.tokens:
            # Patient trying to access admin endpoint
            patient_headers = {"Authorization": f"Bearer {self.tokens['patient']['access_token']}"}
            success, data, status = self.make_request('GET', f"{self.v1_api}/analytics/users", headers=patient_headers)
            
            self.log_test(
                "Role-based access control",
                not success and status == 403,
                f"Status: {status} (should be 403)"
            )

    def run_all_tests(self):
        """Run all test suites"""
        print("🚀 Starting MediFast Backend API Comprehensive Testing")
        print("=" * 60)
        
        start_time = time.time()
        
        # Core API Tests
        self.test_health_check()
        self.test_user_registration()
        self.test_user_authentication()
        self.test_token_refresh()
        self.test_user_profile_operations()
        self.test_admin_user_list()
        
        # Claim Management Tests
        self.test_document_upload()
        self.test_claim_submission()
        self.test_claim_retrieval()
        self.test_claim_details()
        self.test_claim_status_update()
        
        # Notification Tests
        self.test_notifications()
        
        # Analytics Tests
        self.test_analytics()
        
        # Legacy API Tests
        self.test_legacy_endpoints()
        
        # Security Tests
        self.test_security_features()
        
        # Print final results
        end_time = time.time()
        duration = end_time - start_time
        
        print("\n" + "=" * 60)
        print("🏁 TEST RESULTS SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print(f"Duration: {duration:.2f} seconds")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for i, failure in enumerate(self.failed_tests, 1):
                print(f"{i}. {failure}")
        
        return len(self.failed_tests) == 0

def main():
    """Main test execution"""
    tester = MediFastAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())