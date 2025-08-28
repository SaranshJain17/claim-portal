import React, { useState, useRef } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import axios from "axios";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import { Checkbox } from "./components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import { Badge } from "./components/ui/badge";
import { Progress } from "./components/ui/progress";
import { 
  Upload, 
  FileText, 
  CheckCircle, 
  Clock, 
  AlertCircle, 
  User, 
  Hospital, 
  Calendar,
  DollarSign,
  FileCheck,
  Activity,
  Shield,
  Heart
} from "lucide-react";
import { toast, Toaster } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const ClaimSubmission = () => {
  const [file, setFile] = useState(null);
  const [extractedData, setExtractedData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);
  const [submissionSuccess, setSubmissionSuccess] = useState(false);
  const [submittedClaim, setSubmittedClaim] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileSelect = (event) => {
    const selectedFile = event.target.files[0];
    if (selectedFile) {
      // Validate file type
      const validTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg'];
      if (validTypes.includes(selectedFile.type)) {
        setFile(selectedFile);
        setExtractedData(null);
        toast.success("File selected successfully");
      } else {
        toast.error("Please select a PDF or image file");
      }
    }
  };

  const handleFileUpload = async () => {
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API}/upload-claim-document`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data.success) {
        setExtractedData(response.data.extracted_data);
        toast.success("Document processed successfully!");
      }
    } catch (error) {
      console.error('Error uploading file:', error);
      toast.error("Error processing document. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitClaim = async () => {
    if (!extractedData || !consentGiven) {
      toast.error("Please complete all required fields and give consent");
      return;
    }

    setLoading(true);

    try {
      const claimData = {
        ...extractedData,
        file_name: file.name,
        file_type: file.type,
        consent_given: consentGiven
      };

      const response = await axios.post(`${API}/submit-claim`, claimData);
      
      if (response.data) {
        setSubmittedClaim(response.data);
        setSubmissionSuccess(true);
        toast.success("Claim submitted successfully!");
      }
    } catch (error) {
      console.error('Error submitting claim:', error);
      toast.error("Error submitting claim. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFile(null);
    setExtractedData(null);
    setConsentGiven(false);
    setSubmissionSuccess(false);
    setSubmittedClaim(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  if (submissionSuccess && submittedClaim) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-white p-4">
        <div className="max-w-2xl mx-auto pt-8">
          <Card className="shadow-lg border-green-200">
            <CardHeader className="text-center bg-green-50 rounded-t-lg">
              <div className="mx-auto w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
                <CheckCircle className="h-8 w-8 text-green-600" />
              </div>
              <CardTitle className="text-2xl text-green-800">Claim Submitted Successfully!</CardTitle>
              <CardDescription className="text-green-600">
                Your claim has been received and is being processed
              </CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              <div className="space-y-4">
                <div className="bg-blue-50 p-4 rounded-lg">
                  <h3 className="font-semibold text-blue-800 mb-2">Claim Details</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-gray-600">Claim ID:</span>
                      <p className="font-mono text-blue-600">{submittedClaim.id}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Patient:</span>
                      <p className="font-semibold">{submittedClaim.patient_name}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Amount:</span>
                      <p className="font-semibold text-green-600">${submittedClaim.claim_amount}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Status:</span>
                      <Badge variant="outline" className="bg-blue-100 text-blue-800 border-blue-300">
                        {submittedClaim.status}
                      </Badge>
                    </div>
                  </div>
                </div>
                
                <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200">
                  <h4 className="font-semibold text-yellow-800 mb-2 flex items-center">
                    <Clock className="h-4 w-4 mr-2" />
                    What's Next?
                  </h4>
                  <ul className="text-sm text-yellow-700 space-y-1">
                    <li>• Your claim is now in our review queue</li>
                    <li>• You'll receive updates via email and SMS</li>
                    <li>• Processing typically takes 5-7 business days</li>
                    <li>• Track your claim status anytime on your dashboard</li>
                  </ul>
                </div>

                <div className="flex gap-3 pt-4">
                  <Button onClick={resetForm} className="flex-1 bg-blue-600 hover:bg-blue-700">
                    Submit Another Claim
                  </Button>
                  <Button variant="outline" className="flex-1">
                    View Dashboard
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-white p-4">
      <div className="max-w-4xl mx-auto pt-8">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center mb-4">
            <div className="bg-blue-600 p-3 rounded-full">
              <Heart className="h-8 w-8 text-white" />
            </div>
          </div>
          <h1 className="text-4xl font-bold text-blue-900 mb-2">MediFast</h1>
          <p className="text-blue-600 text-lg">Health Claim Settlement Platform</p>
        </div>

        <Card className="shadow-lg">
          <CardHeader className="bg-blue-600 text-white rounded-t-lg">
            <CardTitle className="text-2xl flex items-center">
              <FileCheck className="h-6 w-6 mr-3" />
              Submit New Claim
            </CardTitle>
            <CardDescription className="text-blue-100">
              Upload your medical bills and prescriptions for quick processing
            </CardDescription>
          </CardHeader>
          <CardContent className="p-6">
            <div className="space-y-6">
              {/* Step 1: File Upload */}
              <div className="space-y-4">
                <div className="flex items-center mb-4">
                  <div className="bg-blue-100 text-blue-800 rounded-full w-8 h-8 flex items-center justify-center font-semibold mr-3">1</div>
                  <h3 className="text-lg font-semibold text-gray-900">Upload Medical Documents</h3>
                </div>
                
                <div className="border-2 border-dashed border-blue-300 rounded-lg p-6 text-center">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={handleFileSelect}
                    className="hidden"
                    id="file-upload"
                  />
                  <label htmlFor="file-upload" className="cursor-pointer">
                    <Upload className="h-12 w-12 text-blue-400 mx-auto mb-4" />
                    <p className="text-lg font-medium text-gray-700">
                      {file ? file.name : "Click to upload or drag and drop"}
                    </p>
                    <p className="text-sm text-gray-500 mt-2">
                      PDF, JPG, PNG up to 10MB
                    </p>
                  </label>
                </div>

                {file && (
                  <div className="flex items-center justify-between bg-green-50 p-3 rounded-lg">
                    <div className="flex items-center">
                      <FileText className="h-5 w-5 text-green-600 mr-2" />
                      <span className="text-sm font-medium text-green-800">{file.name}</span>
                    </div>
                    <Button 
                      onClick={handleFileUpload}
                      disabled={loading}
                      className="bg-green-600 hover:bg-green-700"
                      size="sm"
                    >
                      {loading ? "Processing..." : "Process Document"}
                    </Button>
                  </div>
                )}
              </div>

              {/* Step 2: Review Extracted Data */}
              {extractedData && (
                <div className="space-y-4">
                  <div className="flex items-center mb-4">
                    <div className="bg-blue-100 text-blue-800 rounded-full w-8 h-8 flex items-center justify-center font-semibold mr-3">2</div>
                    <h3 className="text-lg font-semibold text-gray-900">Review Extracted Information</h3>
                  </div>
                  
                  <div className="bg-blue-50 p-6 rounded-lg border border-blue-200">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label className="text-blue-800 font-medium flex items-center mb-2">
                          <User className="h-4 w-4 mr-2" />
                          Patient Information
                        </Label>
                        <div className="space-y-2">
                          <Input value={extractedData.patient_name} readOnly className="bg-white" />
                          <Input value={extractedData.patient_id} readOnly className="bg-white" />
                        </div>
                      </div>
                      
                      <div>
                        <Label className="text-blue-800 font-medium flex items-center mb-2">
                          <Hospital className="h-4 w-4 mr-2" />
                          Provider Information
                        </Label>
                        <div className="space-y-2">
                          <Input value={extractedData.hospital_name} readOnly className="bg-white" />
                          <Input value={extractedData.doctor_name} readOnly className="bg-white" />
                        </div>
                      </div>
                      
                      <div>
                        <Label className="text-blue-800 font-medium flex items-center mb-2">
                          <Calendar className="h-4 w-4 mr-2" />
                          Treatment Details
                        </Label>
                        <div className="space-y-2">
                          <Input value={extractedData.treatment_date} readOnly className="bg-white" />
                          <Input value={extractedData.diagnosis} readOnly className="bg-white" />
                        </div>
                      </div>
                      
                      <div>
                        <Label className="text-blue-800 font-medium flex items-center mb-2">
                          <DollarSign className="h-4 w-4 mr-2" />
                          Claim Amount
                        </Label>
                        <Input 
                          value={`$${extractedData.claim_amount}`} 
                          readOnly 
                          className="bg-white font-semibold text-green-600 text-lg"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Step 3: Consent and Submit */}
              {extractedData && (
                <div className="space-y-4">
                  <div className="flex items-center mb-4">
                    <div className="bg-blue-100 text-blue-800 rounded-full w-8 h-8 flex items-center justify-center font-semibold mr-3">3</div>
                    <h3 className="text-lg font-semibold text-gray-900">Consent & Submit</h3>
                  </div>
                  
                  <div className="bg-gray-50 p-4 rounded-lg border">
                    <div className="flex items-start space-x-3">
                      <Checkbox 
                        checked={consentGiven}
                        onCheckedChange={setConsentGiven}
                        id="consent"
                        className="mt-1"
                      />
                      <Label htmlFor="consent" className="text-sm leading-relaxed cursor-pointer">
                        I hereby authorize MediFast to process my health insurance claim and understand that:
                        <ul className="mt-2 ml-4 space-y-1 text-xs text-gray-600">
                          <li>• The information provided is accurate to the best of my knowledge</li>
                          <li>• MediFast may contact my healthcare provider for verification</li>
                          <li>• Processing typically takes 5-7 business days</li>
                          <li>• I will be notified of the claim status via email/SMS</li>
                        </ul>
                      </Label>
                    </div>
                  </div>

                  <Button 
                    onClick={handleSubmitClaim}
                    disabled={!consentGiven || loading}
                    className="w-full bg-blue-600 hover:bg-blue-700 h-12 text-lg font-semibold"
                  >
                    {loading ? (
                      <div className="flex items-center">
                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-3"></div>
                        Submitting Claim...
                      </div>
                    ) : (
                      <div className="flex items-center">
                        <Shield className="h-5 w-5 mr-3" />
                        Submit Claim Securely
                      </div>
                    )}
                  </Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
      <Toaster position="top-right" />
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ClaimSubmission />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;