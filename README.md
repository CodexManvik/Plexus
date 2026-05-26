# ContractLens Enterprise Contract Manager

Full-stack contract lifecycle management platform with:
- FastAPI backend (`backend/app`)
- React + Vite frontend (`frontend/src`)
- Rule-based extraction, citation tracking, verification, approvals, and dashboard analytics

## Backend Setup
1. Create `backend/.env` (optional):
```bash
APP_ENV=development
API_PREFIX=/api
CORS_ORIGINS=http://localhost:5173

# Preferred DB (Oracle or any SQLAlchemy async URL)
# DATABASE_URL=oracle+oracledb_async://user:pass@/?dsn=host:1521/SERVICE

# If DATABASE_URL is not set, backend auto-falls back to SQLite:
# SQLITE_FALLBACK_URL=sqlite+aiosqlite:///./app/fallback_development.db
```

2. Install backend dependencies:
```bash
cd backend
python -m pip install -r requirements.txt
```

3. Start backend:
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Setup
1. Create `frontend/.env`:
```bash
VITE_API_BASE_URL=http://localhost:8000/api
```

2. Install frontend dependencies:
```bash
cd frontend
npm install
```

3. Run frontend:
```bash
npm run dev
```

## Manual End-to-End Flow
1. Login from `/login`.
2. Upload a contract with metadata on `/upload`.
3. Review extracted parameters + dynamic search add on `/extraction`.
4. Verify original vs changed values on `/verification`.
5. Approve/send back on `/approvals`.
6. Review analytics on `/dashboard`.
7. Maintain rules and diagnostics on `/master-maintenance`.
