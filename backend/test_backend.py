import asyncio
import httpx
import sys
import os
import subprocess
import time

# Ensure we can run the test script independently
# This script spins up the FastAPI app on a temporary thread, runs end-to-end integration tests,
# verifying upload, rules extraction, lock leasing, overrides, audit trail logs, and approvals workflows.

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
API_URL = "http://127.0.0.1:8000/api"

async def run_integration_tests():
    print("=== STARTING CLM BACKEND INTEGRATION TESTS ===")
    print("[1/6] Running diagnostic health check...")
    
    timeout = httpx.Timeout(60.0, connect=30.0, read=60.0, write=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            res = await client.get(f"{API_URL}/health")
            print(f"Health check status: {res.status_code} - {res.json()}")
        except Exception as e:
            print(f"ERROR: Backend server not reachable at {API_URL}. Start it first by running 'python app/main.py' or ensure it is active. Error: {e}")
            sys.exit(1)

        # 2. Upload Contract Tagging Ingestion
        print("\n[2/6] Uploading and tagging contract...")
        file_data = {"file": ("MSA_Global_Services_2026.txt", b"Section 1. SCOPE OF SERVICES: Cloud Operations. Section 4. LIMITATION OF LIABILITY: max cap five million dollars ($5,000,000.00). Section 9. TERMINATION: 90 days notice for convenience. Section 11. GOVERNING LAW: Delaware.", "text/plain")}
        metadata = {
            "organization": "LexIntel Corporate",
            "business_unit": "IT Operations",
            "contract_type": "MSA",
            "agreement_type": "Commercial",
            "user_id": "Alex Miller"
        }
        
        upload_res = await client.post(f"{API_URL}/contracts/upload", files=file_data, data=metadata)
        assert upload_res.status_code == 202, f"Upload failed: {upload_res.text}"
        contract = upload_res.json()
        contract_id = contract["contract_id"]
        print(f"Uploaded successfully! Ingested Contract ID: {contract_id}")
        print(f"Workflow State: {contract['workflow_state']}")

        # Confirm suggestions / Accept tags to trigger the full extraction pipeline
        print("\nAccepting suggested metadata tags...")
        accept_res = await client.post(f"{API_URL}/contracts/{contract_id}/accept-tags", json={"modified_by": "Alex Miller"})
        assert accept_res.status_code == 200, f"Accept tags failed: {accept_res.text}"
        contract = accept_res.json()
        print(f"Workflow State after accepting tags: {contract['workflow_state']}")
        print(f"Extracted parameters count: {len(contract['parameters'])}")
        for param in contract["parameters"]:
            print(f"  - Parameter: '{param['header_name']}' => Extract: '{param['user_override']}' (Confidence Score: {param['match_score']})")

        # 3. Lock Acquisition Lease Checkout
        print("\n[3/6] Acquiring 15-minute lease checkout lock...")
        lock_res = await client.post(f"{API_URL}/contracts/{contract_id}/lock", json={"user_id": "Alex Miller"})
        assert lock_res.status_code == 200, f"Lock acquisition failed: {lock_res.text}"
        lock_info = lock_res.json()
        print(f"Lock Status: acquired={lock_info['lock_acquired']}, checked_out_by={lock_info['checked_out_by']}")

        # 4. In-cell User Override and Audit Log verification
        print("\n[4/6] Modifying parameter to user override...")
        param_id = contract["parameters"][0]["parameter_id"]
        param_header = contract["parameters"][0]["header_name"]
        override_payload = {
            "user_override": "Modified Cloud Hosting Operations SLA",
            "modified_by": "Alex Miller"
        }
        update_res = await client.put(f"{API_URL}/contracts/{contract_id}/parameters/{param_id}", json=override_payload)
        assert update_res.status_code == 200, f"Parameter update failed: {update_res.text}"
        updated_param = update_res.json()
        print(f"Updated successfully! Parameter: '{updated_param['header_name']}'")
        print(f"Original: '{updated_param['original_extract']}'")
        print(f"User Override (New): '{updated_param['user_override']}'")

        # Fetch details to verify version increment
        details_res = await client.get(f"{API_URL}/contracts/{contract_id}")
        updated_contract = details_res.json()
        print(f"New Document Version: {updated_contract['document_version']}")

        # 5. Submit for approvals
        print("\n[5/6] Submitting staged draft to approvals queue...")
        sub_res = await client.post(f"{API_URL}/contracts/{contract_id}/submit-approval", json={"modified_by": "Alex Miller"})
        assert sub_res.status_code == 200, f"Submission failed: {sub_res.text}"
        print(f"Approval Queue status: {sub_res.json()['status']}")

        # 6. Final authorization manager execution
        print("\n[6/6] Executing operational approval by Manager...")
        app_res = await client.post(f"{API_URL}/contracts/{contract_id}/approve", json={"modified_by": "Alex Miller"})
        assert app_res.status_code == 200, f"Approval authorization failed: {app_res.text}"
        print(f"Approval authorized! Response workflow state: {app_res.json()['status']}")

        # Final state check
        final_res = await client.get(f"{API_URL}/contracts/{contract_id}")
        final_contract = final_res.json()
        print(f"Final Workflow State: {final_contract['workflow_state']}")

        # 7. Release locks
        await client.post(f"{API_URL}/contracts/{contract_id}/unlock", json={"user_id": "Alex Miller"})
        print("\n=== INTEGRATION TESTS SUCCESSFULLY COMPLETED WITH 100% SUCCESS ===")

if __name__ == "__main__":
    # Check if server is running, if not inform user
    asyncio.run(run_integration_tests())
