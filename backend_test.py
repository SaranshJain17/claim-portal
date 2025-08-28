import requests
import sys
import json
import io
from datetime import datetime

class MediFastAPITester:
    def __init__(self, base_url="https://claim-portal-1.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.claim_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {}
        
        if files is None:
            headers['Content-Type'] = 'application/json'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files)
                else:
                    response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test the root API endpoint"""
        success, response = self.run_test(
            "Root API Endpoint",
            "GET",
            "",
            200
        )
        return success

    def test_upload_claim_document(self):
        """Test file upload and mock OCR processing"""
        # Create a mock PDF file
        mock_file_content = b"Mock PDF content for testing"
        files = {
            'file': ('test_medical_bill.pdf', io.BytesIO(mock_file_content), 'application/pdf')
        }
        
        success, response = self.run_test(
            "Upload Claim Document (Mock OCR)",
            "POST",
            "upload-claim-document",
            200,
            files=files
        )
        
        if success and response:
            # Verify response structure
            required_fields = ['success', 'extracted_data', 'file_info']
            for field in required_fields:
                if field not in response:
                    print(f"❌ Missing field in response: {field}")
                    return False
            
            # Verify extracted data structure
            extracted_data = response.get('extracted_data', {})
            required_data_fields = [
                'patient_name', 'patient_id', 'hospital_name', 
                'doctor_name', 'treatment_date', 'claim_amount', 
                'diagnosis', 'treatment_type'
            ]
            
            for field in required_data_fields:
                if field not in extracted_data:
                    print(f"❌ Missing field in extracted_data: {field}")
                    return False
            
            print(f"✅ Mock OCR extracted data successfully")
            return True
        
        return False

    def test_submit_claim(self):
        """Test claim submission"""
        claim_data = {
            "patient_name": "John Smith",
            "patient_id": "P123456789",
            "hospital_name": "City General Hospital",
            "doctor_name": "Dr. Sarah Johnson",
            "treatment_date": "2024-12-15",
            "claim_amount": 2500.00,
            "diagnosis": "Acute appendicitis",
            "treatment_type": "Emergency Surgery",
            "file_name": "test_medical_bill.pdf",
            "file_type": "application/pdf",
            "consent_given": True
        }
        
        success, response = self.run_test(
            "Submit Claim",
            "POST",
            "submit-claim",
            200,
            data=claim_data
        )
        
        if success and response:
            # Store claim ID for later tests
            self.claim_id = response.get('id')
            if self.claim_id:
                print(f"✅ Claim submitted with ID: {self.claim_id}")
                
                # Verify response structure
                required_fields = [
                    'id', 'patient_name', 'claim_amount', 'status', 
                    'submission_date', 'consent_given'
                ]
                
                for field in required_fields:
                    if field not in response:
                        print(f"❌ Missing field in response: {field}")
                        return False
                
                return True
            else:
                print(f"❌ No claim ID returned in response")
                return False
        
        return False

    def test_get_all_claims(self):
        """Test retrieving all claims"""
        success, response = self.run_test(
            "Get All Claims",
            "GET",
            "claims",
            200
        )
        
        if success and isinstance(response, list):
            print(f"✅ Retrieved {len(response)} claims")
            return True
        elif success:
            print(f"❌ Expected list response, got: {type(response)}")
            return False
        
        return False

    def test_get_specific_claim(self):
        """Test retrieving a specific claim by ID"""
        if not self.claim_id:
            print(f"❌ No claim ID available for testing")
            return False
        
        success, response = self.run_test(
            f"Get Specific Claim ({self.claim_id})",
            "GET",
            f"claims/{self.claim_id}",
            200
        )
        
        if success and response:
            if response.get('id') == self.claim_id:
                print(f"✅ Successfully retrieved claim {self.claim_id}")
                return True
            else:
                print(f"❌ Claim ID mismatch: expected {self.claim_id}, got {response.get('id')}")
                return False
        
        return False

    def test_get_nonexistent_claim(self):
        """Test retrieving a non-existent claim"""
        fake_id = "non-existent-claim-id"
        success, response = self.run_test(
            "Get Non-existent Claim (Should Fail)",
            "GET",
            f"claims/{fake_id}",
            404
        )
        return success

    def test_invalid_file_upload(self):
        """Test uploading invalid file type"""
        # Create a mock text file (invalid type)
        mock_file_content = b"This is not a valid medical document"
        files = {
            'file': ('test.txt', io.BytesIO(mock_file_content), 'text/plain')
        }
        
        # This should still work as backend doesn't validate file type, only frontend does
        success, response = self.run_test(
            "Upload Invalid File Type",
            "POST",
            "upload-claim-document",
            200,  # Backend accepts any file type
            files=files
        )
        return success

    def test_submit_claim_without_consent(self):
        """Test submitting claim without consent"""
        claim_data = {
            "patient_name": "Jane Doe",
            "patient_id": "P987654321",
            "hospital_name": "Metro Medical Center",
            "doctor_name": "Dr. Michael Chen",
            "treatment_date": "2024-12-10",
            "claim_amount": 1850.75,
            "diagnosis": "Pneumonia",
            "treatment_type": "Inpatient Treatment",
            "file_name": "test_bill.pdf",
            "file_type": "application/pdf",
            "consent_given": False  # No consent given
        }
        
        success, response = self.run_test(
            "Submit Claim Without Consent",
            "POST",
            "submit-claim",
            200,  # Backend doesn't validate consent, frontend does
            data=claim_data
        )
        return success

def main():
    print("🏥 MediFast Health Claim Settlement Platform - API Testing")
    print("=" * 60)
    
    tester = MediFastAPITester()
    
    # Run all tests
    tests = [
        tester.test_root_endpoint,
        tester.test_upload_claim_document,
        tester.test_submit_claim,
        tester.test_get_all_claims,
        tester.test_get_specific_claim,
        tester.test_get_nonexistent_claim,
        tester.test_invalid_file_upload,
        tester.test_submit_claim_without_consent
    ]
    
    for test in tests:
        test()
    
    # Print final results
    print("\n" + "=" * 60)
    print(f"📊 FINAL RESULTS")
    print(f"Tests Run: {tester.tests_run}")
    print(f"Tests Passed: {tester.tests_passed}")
    print(f"Tests Failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success Rate: {(tester.tests_passed/tester.tests_run)*100:.1f}%")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed! Backend API is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())