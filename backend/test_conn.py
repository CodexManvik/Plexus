import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings

async def test_connection():
    # Try different connection URL formats
    urls = [
        # Format 1: Using dsn parameter in query string
        f"oracle+oracledb_async://{settings.oracle_db_user}:{settings.oracle_db_password}@/?dsn=localhost:1521/FREEPDB1",
        # Format 2: Using service_name in query string
        f"oracle+oracledb_async://{settings.oracle_db_user}:{settings.oracle_db_password}@localhost:1521/?service_name=FREEPDB1",
        # Format 3: Using direct SID format if FREE is the SID
        f"oracle+oracledb_async://{settings.oracle_db_user}:{settings.oracle_db_password}@localhost:1521/FREE"
    ]
    
    for url in urls:
        print(f"\nTesting connection with URL: {url.split('@')[0]}@...")
        try:
            engine = create_async_engine(url, echo=False)
            async with engine.connect() as conn:
                result = await conn.execute("SELECT 'Connection Successful' FROM DUAL")
                row = result.fetchone()
                print(f"SUCCESS: {row[0]}")
                return url
        except Exception as e:
            print(f"FAILED: {e}")
            
    return None

if __name__ == "__main__":
    asyncio.run(test_connection())
