from fastapi.testclient import TestClient
import sys
import traceback

# Prepend parent directory to path to ensure proper package imports
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app

client = TestClient(app)

def run_test():
    print("=== STARTING IN-MEMORY VERIFICATION TEST ===")
    
    file_data = {
        "file": ("test_contract.txt", b"Section 1. SCOPE OF SERVICES: Cloud Operations. Section 4. LIMITATION OF LIABILITY: max cap five million dollars ($5,000,000.00). Section 9. TERMINATION: 90 days notice for convenience.")
    }
    metadata = {
        "organization": "LexIntel Corporate",
        "business_unit": "IT Operations",
        "contract_type": "MSA",
        "agreement_type": "Commercial",
        "user_id": "Alex Miller"
    }

    try:
        print("Calling /api/contracts/upload...")
        # FastAPI TestClient synchronously handles async routes
        response = client.post("/api/contracts/upload", files=file_data, data=metadata)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 500:
            print("\nError 500: Internal Server Error occurred.")
    except Exception as e:
        print("\nException raised during TestClient call:")
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
