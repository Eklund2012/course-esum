# Course Evaluation Summarizer (`course-esum`)

An asynchronous microservice that fetches, parses, and summarizes university course evaluation reports (*kursutvärderingsanalyser*) using **Google Gemini 2.5 Flash** and **FastAPI**.

---

## Features

| Feature | Details |
|---|---|
| **Automated University Fetching** | Enter a Karlstad University course code (e.g. `DVAE24`) to automatically scrape, download, and analyze official PDF evaluation reports |
| **Multimodal PDF Ingestion** | Streams PDF byte documents directly into Gemini, preserving multi-column layouts, score tables, and graphs without OCR degradation |
| **Async 202 Architecture** | Long-running AI inference is decoupled from HTTP via background tasks |
| **Real-Time SSE Streaming** | Subscribe to `GET /api/v1/evaluations/jobs/{id}/stream` for live progress events |
| **Pluggable Provider Architecture** | Clean `CourseEvaluationProvider` abstraction — easily add support for other institutions |
| **Persistent State & History** | SQLModel/SQLAlchemy tracks all jobs, summaries, and evaluation trends |
| **Security & Rate Limiting** | `X-API-Key` header auth + per-client rate limiting via `slowapi` |
| **Gemini Retry & Timeout** | Exponential backoff with full jitter on 429/5xx errors; configurable hard timeout prevents hung workers |
| **Strict File Validation** | MIME type, magic bytes, size limit (default 15 MB), empty-file, password-protection, and structural integrity checks |
| **Orphaned Job Recovery** | Startup hook automatically fails jobs left in `PROCESSING` after a server restart |
| **Clean Error Responses** | All API errors return structured JSON — raw tracebacks never reach clients |

---

## Requirements

- **Python 3.11+**
- A **Google Gemini API key** — [get one here](https://aistudio.google.com/app/apikey)

---

## Local Setup

### 1. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in at minimum:

```ini
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Recommended: change in any non-local environment
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
API_KEY=dev-secret-key-12345

# Database (SQLite by default — no extra setup needed)
DATABASE_URL=sqlite:///./course_esum.db
```

See [`.env.example`](.env.example) for the full list of tunable settings.

### 3. Database initialization

The database tables are created automatically on first startup via `SQLModel.metadata.create_all()`. There are **no manual migration steps** required for SQLite. If you switch to PostgreSQL, set `DATABASE_URL` accordingly and run the service once to bootstrap the schema.

### 4. Run the development server

A convenience script at the project root sets `PYTHONPATH` and starts uvicorn in one command:

```powershell
.\run.ps1
```

If PowerShell blocks unsigned scripts, run this once first:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

> **Manual equivalent** (if you prefer not to use the script):
> ```powershell
> $env:PYTHONPATH = "src"
> .\.venv\Scripts\python.exe -m uvicorn course_esum.main:app --reload --port 8000
> ```

Interactive API documentation is available once the server is running:

- **Swagger UI**: <http://localhost:8000/docs>
- **ReDoc**: <http://localhost:8000/redoc>
- **Web UI**: <http://localhost:8000/>

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `GEMINI_MAX_RETRIES` | `4` | Max retry attempts on transient Gemini errors (429 / 5xx) |
| `GEMINI_BASE_DELAY_MS` | `500` | Initial backoff window in milliseconds |
| `GEMINI_MAX_DELAY_MS` | `30000` | Backoff ceiling in milliseconds |
| `GEMINI_TIMEOUT_SECS` | `120` | Hard wall-clock timeout per Gemini call |
| `API_KEY` | `dev-secret-key-12345` | Bearer token for `X-API-Key` authentication |
| `MAX_UPLOAD_SIZE_MB` | `15` | Maximum size per uploaded PDF file |
| `DATABASE_URL` | `sqlite:///./course_esum.db` | SQLAlchemy database URL |
| `RATE_LIMIT_PER_MINUTE` | `60/minute` | Requests per minute per IP |
| `DEFAULT_MAX_REPORTS` | `3` | Default number of past term reports to analyze |
| `APP_ENV` | `development` | Environment label (`development` / `production`) |
| `DEBUG` | `false` | Enable SQLAlchemy query logging |

---

## API Reference

All requests require the `X-API-Key` header.

### POST `/api/v1/evaluations/jobs/fetch` — Submit by course code

```http
POST /api/v1/evaluations/jobs/fetch
Content-Type: application/json
X-API-Key: dev-secret-key-12345

{
  "course_code": "DVAE24",
  "output_language": "English",
  "max_reports": 2
}
```

**Response `202 Accepted`:**
```json
{
  "job_id": "job_a1b2c3d4e5f6",
  "status": "PENDING",
  "input_type": "COURSE_CODE",
  "course_code": "DVAE24",
  "created_at": "2026-09-25T18:55:00Z",
  "links": {
    "status": "/api/v1/evaluations/jobs/job_a1b2c3d4e5f6",
    "stream": "/api/v1/evaluations/jobs/job_a1b2c3d4e5f6/stream"
  }
}
```

### POST `/api/v1/evaluations/jobs/upload` — Submit PDF file(s)

```http
POST /api/v1/evaluations/jobs/upload
Content-Type: multipart/form-data
X-API-Key: dev-secret-key-12345

files: [binary PDF files]   # MIME type must be application/pdf; max 15 MB each
output_language: English
```

**Validation rules:**
- MIME type must be `application/pdf` or `application/x-pdf`
- File must start with `%PDF` magic bytes
- File must not be empty or exceed `MAX_UPLOAD_SIZE_MB`
- File must not be password-protected or structurally corrupt

### GET `/api/v1/evaluations/jobs/{job_id}` — Poll job status

```http
GET /api/v1/evaluations/jobs/job_a1b2c3d4e5f6
X-API-Key: dev-secret-key-12345
```

**Response `200 OK`:**
```json
{
  "job_id": "job_a1b2c3d4e5f6",
  "status": "COMPLETED",
  "input_type": "COURSE_CODE",
  "course_code": "DVAE24",
  "output_language": "English",
  "result": {
    "course_name_and_code": "Aktuell forskning inom datanätverk (DVAE24)",
    "positive_summary": ["..."],
    "critique_summary": ["..."],
    "workload": "Too high",
    "trend_over_time": "...",
    "reports_analyzed": ["HT-25 (KAU-47889)", "HT-24 (KAU-45494)"],
    "respondents_count": 18,
    "registered_count": 32,
    "response_rate_percent": 56.3
  }
}
```


### GET `/api/v1/evaluations/jobs/{job_id}/stream` — Real-time SSE

Pass the API key as a **query parameter** (browsers do not support custom headers in `EventSource`):

```
GET /api/v1/evaluations/jobs/job_a1b2c3d4e5f6/stream?api_key=dev-secret-key-12345
```

Events emitted:

| Event | Payload |
|---|---|
| `status` | `{"job_id": "...", "status": "PENDING"}` |
| `update` | `{"status": "PROCESSING", "message": "Fetching..."}` |
| `update` | `{"status": "COMPLETED", "message": "Evaluation summary ready.", "data": {...}}` |
| `update` | `{"status": "FAILED", "error": "human-readable message"}` |
| `ping` | `{"timestamp": "keep-alive"}` (every 30 s) |

### GET `/api/v1/evaluations/history` — Evaluation history

```http
GET /api/v1/evaluations/history?course_code=DVAE24&limit=10
X-API-Key: dev-secret-key-12345
```

---

## Running Tests

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

To also see short tracebacks on failures:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

The test suite uses an **in-memory SQLite database** per test function and mocks external dependencies (Gemini, KAU portal) so no real API calls are made.

---

## Docker

```powershell
docker compose up -d --build
docker compose logs -f
```

The `docker-compose.yml` mounts a local `.env` file. Ensure it is populated before building.

---

## Project Structure

```
src/course_esum/
├── api/
│   ├── dependencies.py        # Shared FastAPI dependency helpers
│   └── v1/endpoints/
│       ├── evaluations.py     # POST /jobs/fetch, POST /jobs/upload, GET /history
│       ├── jobs.py            # GET /jobs/{id}, GET /jobs/{id}/stream (SSE)
│       └── health.py          # GET /health
├── config.py                  # Pydantic Settings (loaded from .env)
├── core/
│   ├── database.py            # SQLModel engine + session factory
│   ├── security.py            # API key verification
│   └── startup.py             # Orphaned job sweep on boot
├── models/                    # SQLModel table definitions
├── schemas/                   # Pydantic request/response models
├── services/
│   ├── gemini_retry.py        # Exponential backoff retry wrapper
│   ├── job_runner.py          # Background job orchestration
│   ├── summarizer.py          # Gemini multimodal PDF summarization
│   └── providers/
│       ├── kau_provider.py    # Karlstad University scraper
│       └── mock_provider.py   # Test/demo provider
└── static/                    # Bundled web frontend (HTML/CSS/JS)
```
