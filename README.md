# Plexus Local ICMS

This workspace provides a local-only stack for the Intelligent Contract Management System with pgvector, FastAPI, and llama.cpp.

## Quick start

1) Start pgvector

```
docker compose up -d
```

2) Copy env file and adjust as needed

```
copy .env.example .env
```

3) Install backend dependencies

```
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

4) Start llama.cpp server (edit model path if needed)

```
.\scripts\start-llama-server.ps1
```

5) Run the API

```
.\scripts\run-backend.ps1
```

## API

- `GET /health`
- `POST /contracts`
- `POST /contracts/{contract_id}/extract`
- `PATCH /parameters/{parameter_id}`
- `POST /search`
