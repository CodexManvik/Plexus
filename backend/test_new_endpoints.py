#!/usr/bin/env python
"""
Comprehensive test for all new endpoints added in the latest refactor
Tests metadata, dashboard, verification, and maintenance endpoints
"""

import httpx
import asyncio
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api"

async def test_new_endpoints():
    """Test all new endpoints"""
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("\n=== NEW ENDPOINTS TEST SUITE ===\n")
        
        # ============ METADATA ENDPOINTS ============
        print("Testing Metadata Endpoints...")
        print("-" * 50)
        
        # Test organizations
        try:
            resp = await client.get(f"{BASE_URL}/metadata/organizations")
            print(f"✓ GET /metadata/organizations: {resp.status_code}")
            print(f"  Organizations: {resp.json()}\n")
        except Exception as e:
            print(f"✗ Metadata Organizations Error: {e}\n")
        
        # Test business units
        try:
            resp = await client.get(f"{BASE_URL}/metadata/business-units")
            print(f"✓ GET /metadata/business-units: {resp.status_code}")
            print(f"  Business Units: {resp.json()}\n")
        except Exception as e:
            print(f"✗ Metadata Business Units Error: {e}\n")
        
        # Test contract types
        try:
            resp = await client.get(f"{BASE_URL}/metadata/contract-types")
            print(f"✓ GET /metadata/contract-types: {resp.status_code}")
            print(f"  Contract Types: {resp.json()}\n")
        except Exception as e:
            print(f"✗ Metadata Contract Types Error: {e}\n")
        
        # Test agreement types
        try:
            resp = await client.get(f"{BASE_URL}/metadata/agreement-types")
            print(f"✓ GET /metadata/agreement-types: {resp.status_code}")
            print(f"  Agreement Types: {resp.json()}\n")
        except Exception as e:
            print(f"✗ Metadata Agreement Types Error: {e}\n")
        
        # ============ DASHBOARD ENDPOINTS ============
        print("\nTesting Dashboard Endpoints...")
        print("-" * 50)
        
        # Test dashboard stats
        try:
            resp = await client.get(f"{BASE_URL}/dashboard/stats")
            print(f"✓ GET /dashboard/stats: {resp.status_code}")
            data = resp.json()
            print(f"  Total Contracts: {data.get('total_contracts', 'N/A')}")
            print(f"  Pending Approvals: {data.get('pending_approvals', 'N/A')}")
            print(f"  Expired Contracts: {data.get('expired_contracts', 'N/A')}\n")
        except Exception as e:
            print(f"✗ Dashboard Stats Error: {e}\n")
        
        # Test recent contracts
        try:
            resp = await client.get(f"{BASE_URL}/dashboard/recent?limit=5")
            print(f"✓ GET /dashboard/recent: {resp.status_code}")
            data = resp.json()
            print(f"  Recent Contracts Count: {len(data.get('data', []))}\n")
        except Exception as e:
            print(f"✗ Dashboard Recent Error: {e}\n")
        
        # Test pending approvals
        try:
            resp = await client.get(f"{BASE_URL}/dashboard/pending-approvals")
            print(f"✓ GET /dashboard/pending-approvals: {resp.status_code}")
            data = resp.json()
            print(f"  Pending Approvals Count: {len(data.get('data', []))}\n")
        except Exception as e:
            print(f"✗ Dashboard Pending Approvals Error: {e}\n")
        
        # ============ MAINTENANCE ENDPOINTS ============
        print("\nTesting Maintenance Endpoints...")
        print("-" * 50)
        
        # Test status
        try:
            resp = await client.get(f"{BASE_URL}/maintenance/status")
            print(f"✓ GET /maintenance/status: {resp.status_code}")
            data = resp.json()
            print(f"  System Status: {data.get('status', 'N/A')}")
            print(f"  Database: {data.get('database', 'N/A')}")
            print(f"  API: {data.get('api', 'N/A')}\n")
        except Exception as e:
            print(f"✗ Maintenance Status Error: {e}\n")
        
        # Test logs
        try:
            resp = await client.get(f"{BASE_URL}/maintenance/logs?limit=10")
            print(f"✓ GET /maintenance/logs: {resp.status_code}")
            data = resp.json()
            print(f"  Error Logs Count: {len(data.get('data', []))}\n")
        except Exception as e:
            print(f"✗ Maintenance Logs Error: {e}\n")
        
        # Test sync
        try:
            resp = await client.post(f"{BASE_URL}/maintenance/sync")
            print(f"✓ POST /maintenance/sync: {resp.status_code}")
            data = resp.json()
            print(f"  Sync Status: {data.get('status', 'N/A')}\n")
        except Exception as e:
            print(f"✗ Maintenance Sync Error: {e}\n")
        
        # ============ CONTRACT SEARCH & AUDIT ============
        print("\nTesting Contract Advanced Endpoints...")
        print("-" * 50)
        
        # Test search
        try:
            resp = await client.get(f"{BASE_URL}/contracts/search?query=&org=&status=")
            print(f"✓ GET /contracts/search: {resp.status_code}")
            data = resp.json()
            print(f"  Search Results Count: {len(data.get('data', []))}\n")
        except Exception as e:
            print(f"✗ Contract Search Error: {e}\n")
        
        # First, get a contract ID for audit testing
        try:
            resp = await client.get(f"{BASE_URL}/contracts")
            contracts = resp.json()
            if contracts and len(contracts) > 0:
                contract_id = contracts[0]['contract_id']
                
                # Test audit trail
                try:
                    resp = await client.get(f"{BASE_URL}/contracts/{contract_id}/audit")
                    print(f"✓ GET /contracts/{contract_id}/audit: {resp.status_code}")
                    data = resp.json()
                    print(f"  Audit Records: {len(data.get('audit_trail', []))}\n")
                except Exception as e:
                    print(f"✗ Contract Audit Error: {e}\n")
                
                # Test parameters
                try:
                    resp = await client.get(f"{BASE_URL}/contracts/{contract_id}/parameters")
                    print(f"✓ GET /contracts/{contract_id}/parameters: {resp.status_code}")
                    data = resp.json()
                    print(f"  Parameters Count: {len(data.get('parameters', []))}\n")
                except Exception as e:
                    print(f"✗ Contract Parameters Error: {e}\n")
                
                # Test extraction status
                try:
                    resp = await client.get(f"{BASE_URL}/contracts/{contract_id}/extraction-status")
                    print(f"✓ GET /contracts/{contract_id}/extraction-status: {resp.status_code}")
                    data = resp.json()
                    print(f"  Status: {data.get('status', 'N/A')}")
                    print(f"  Total Parameters: {data.get('total', 'N/A')}\n")
                except Exception as e:
                    print(f"✗ Contract Extraction Status Error: {e}\n")
                
                # Test verification
                try:
                    # Get parameters first to get a valid parameter ID
                    resp = await client.get(f"{BASE_URL}/contracts/{contract_id}/parameters")
                    params = resp.json().get('parameters', [])
                    if params and len(params) > 0:
                        param_id = params[0]['parameter_id']
                        resp = await client.post(
                            f"{BASE_URL}/verification/{contract_id}/{param_id}/verify",
                            json={"is_correct": True}
                        )
                        print(f"✓ POST /verification/{contract_id}/{param_id}/verify: {resp.status_code}")
                        data = resp.json()
                        print(f"  Response: {data}\n")
                except Exception as e:
                    print(f"✗ Verification Error: {e}\n")
        except Exception as e:
            print(f"✗ Error getting contracts for audit testing: {e}\n")
        
        print("\n=== TEST SUITE COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(test_new_endpoints())
