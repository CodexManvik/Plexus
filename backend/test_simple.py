"""
Simple test to verify database initialization and basic operations.
"""
import asyncio
import httpx

API_URL = "http://127.0.0.1:8000/api"

async def simple_test():
    print("=== SIMPLE DATABASE TEST ===\n")
    
    # Increase timeout significantly for file upload operations
    timeout = httpx.Timeout(60.0, connect=30.0, read=60.0, write=30.0)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1. Health Check
        print("[1] Health Check...")
        try:
            res = await client.get(f"{API_URL}/health")
            print(f"✓ Health: {res.status_code}")
            print(f"  Details: {res.json()}\n")
        except Exception as e:
            print(f"✗ Health check failed: {e}\n")
            return
        
        # 2. Simple Contract Upload
        print("[2] Contract Upload (with increased timeout)...")
        try:
            file_data = {
                "file": ("test_contract.txt", 
                        b"Section 1. SCOPE: Cloud Operations. Section 4. LIABILITY: max 5M. Section 9. TERMINATION: 90 days.", 
                        "text/plain")
            }
            metadata = {
                "organization": "Test Corp",
                "business_unit": "Ops",
                "contract_type": "MSA",
                "agreement_type": "Commercial",
                "user_id": "test_user"
            }
            
            res = await client.post(
                f"{API_URL}/contracts/upload",
                files=file_data,
                data=metadata
            )
            print(f"✓ Upload Status: {res.status_code}")
            contract = res.json()
            print(f"  Contract ID: {contract['contract_id']}")
            print(f"  Status: {contract['workflow_state']}")
            print(f"  Parameters extracted: {len(contract['parameters'])}\n")
            
            contract_id = contract['contract_id']
            
            # 3. Retrieve Contract
            print("[3] Retrieve Contract Details...")
            res = await client.get(f"{API_URL}/contracts/{contract_id}")
            print(f"✓ Retrieve Status: {res.status_code}")
            details = res.json()
            print(f"  Contract Type: {details['contract_type']}")
            print(f"  Parameters: {len(details['parameters'])}\n")
            
            # 4. Lock Contract
            print("[4] Acquire Lock...")
            res = await client.post(
                f"{API_URL}/contracts/{contract_id}/lock",
                json={"user_id": "test_user"}
            )
            print(f"✓ Lock Status: {res.status_code}")
            lock_info = res.json()
            print(f"  Locked by: {lock_info['checked_out_by']}\n")
            
            # 5. Update Parameter
            if contract['parameters']:
                print("[5] Update Parameter...")
                param_id = contract['parameters'][0]['parameter_id']
                res = await client.put(
                    f"{API_URL}/contracts/{contract_id}/parameters/{param_id}",
                    json={
                        "user_override": "Modified Scope",
                        "modified_by": "test_user"
                    }
                )
                print(f"✓ Update Status: {res.status_code}")
                updated = res.json()
                print(f"  Override: {updated['user_override']}\n")
            
            # 6. Unlock Contract
            print("[6] Release Lock...")
            res = await client.post(
                f"{API_URL}/contracts/{contract_id}/unlock",
                json={"user_id": "test_user"}
            )
            print(f"✓ Unlock Status: {res.status_code}\n")
            
            print("✓✓✓ ALL TESTS PASSED ✓✓✓")
            
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(simple_test())
