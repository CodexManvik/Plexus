import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=60.0) as client:
        file_data = {
            'file': ('test.txt', b'Test content', 'text/plain')
        }
        metadata = {
            'organization': 'Test Corp',
            'business_unit': 'Ops',
            'contract_type': 'MSA',
            'agreement_type': 'Commercial',
            'user_id': 'test_user'
        }
        res = await client.post('http://localhost:8000/api/contracts/upload', files=file_data, data=metadata)
        print(f'Status: {res.status_code}')
        if res.status_code == 202:
            data = res.json()
            print(f"Contract ID: {data.get('contract_id')}")
            print(f"Status: {data.get('contract_status')}")
        else:
            print(f'Error: {res.text[:200]}')

asyncio.run(test())
