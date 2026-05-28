"""
Initializes database tables for the CLM backend using SQLAlchemy models.
Compatible with both Oracle (if configured) and SQLite fallback.
"""
import asyncio

from app.database import AsyncSessionLocal, Base, engine, get_database_driver
from app.services.bootstrap import seed_defaults


async def init_database():
    async with engine.begin() as conn:
        print("Dropping existing tables to clear any stale schemas...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Creating fresh database tables...")
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await seed_defaults(session)

    print(f"Database initialized successfully using driver: {get_database_driver()}")


if __name__ == "__main__":
    asyncio.run(init_database())
