from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

Base = declarative_base()

DATABASE_URL = settings.resolved_database_url()


def _configure_oracle_client() -> None:
    if not DATABASE_URL.startswith("oracle+oracledb"):
        return
    if not settings.oracle_thick_mode:
        return

    import oracledb

    kwargs = {}
    if settings.oracle_client_lib_dir:
        kwargs["lib_dir"] = settings.oracle_client_lib_dir
    oracledb.init_oracle_client(**kwargs)


_configure_oracle_client()

try:
    engine = create_async_engine(
        DATABASE_URL,
        echo=settings.app_env == "development",
        pool_pre_ping=True,
    )
except ModuleNotFoundError as exc:
    if "oracledb" in str(exc).lower() and settings.database_backend == "auto":
        DATABASE_URL = settings.resolved_sqlite_url()
        engine = create_async_engine(
            DATABASE_URL,
            echo=settings.app_env == "development",
            pool_pre_ping=True,
        )
    elif "oracledb" in str(exc).lower():
        raise RuntimeError(
            "Oracle 26ai mode requires the python-oracledb package. "
            "Install backend requirements or set DATABASE_BACKEND=sqlite for local demo mode."
        ) from exc
    else:
        raise

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def get_database_driver() -> str:
    return engine.url.drivername


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
