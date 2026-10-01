# Course Evaluation Summarizer (`course-esum`)

An asynchronous microservice that analyzes and summarizes university course evaluation reports (*kursutvärderingsanalyser*) using **Google Gemini 2.5 Flash** and **FastAPI**.

---

## Features

- **Automated University Fetching**: Enter a Karlstad University course code (e.g. `DVAE24`, `DVAE23`, `ISGB11`) to automatically scrape, download, and analyze official PDF evaluation reports in-memory without manual file uploads.
- **Multimodal PDF Ingestion**: Directly streams PDF byte documents into Gemini 2.5 Flash, preserving multi-column layouts, score distributions, and tables without OCR degradation.
- **Asynchronous 202 Accepted Architecture**: Decouples client HTTP connections from long-running LLM inference via background task execution.
- **Real-Time SSE Streaming**: Clients can subscribe to `GET /api/v1/evaluations/jobs/{job_id}/stream` for instant push notifications as evaluations process.
- **Pluggable Provider Architecture**: Clean `CourseEvaluationProvider` abstraction supporting Karlstad University (`KarlstadUniversityProvider`) and mock data (`MockCourseProvider`), easily extensible to other institutions.
- **Persistent State & History**: SQLModel (SQLAlchemy) database tracking jobs, courses, positive/critique summaries, workloads, and multi-year trends.
- **Security & Rate Limiting**: `X-API-Key` authentication header and per-client request rate limiting via `slowapi`.
- **Gemini Retry & Resilience**: Exponential backoff with jitter on Gemini API 429/503 errors via `tenacity`.
- **Orphaned Job Recovery**: Startup lifecycle hook automatically fails jobs left in `PROCESSING` state after a server restart.

---

## Requirements

- Python 3.11+
- A Google Gemini API key ([get one here](https://aistudio.google.com/app/apikey))

---

## Setup

### 1. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```powershell
Copy-Item .env.example .env
```

Minimum required values:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
API_KEY=dev-secret-key-12345
DATABASE_URL=sqlite:///./course_esum.db
APP_ENV=development
```

### 3. Run the service

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn course_esum.main:app --reload --port 8000
```

API documentation is available at:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## API Reference

All requests require the `X-API-Key` header (default in development: `dev-secret-key-12345`).

### Submit evaluation by course code

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

**Response (`202 Accepted`)**:
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

### Poll job status and result

```http
GET /api/v1/evaluations/jobs/job_a1b2c3d4e5f6
X-API-Key: dev-secret-key-12345
```

**Response (`200 OK`)**:
```json
{
  "job_id": "job_a1b2c3d4e5f6",
  "status": "COMPLETED",
  "input_type": "COURSE_CODE",
  "course_code": "DVAE24",
  "output_language": "English",
  "result": {
    "course_name_and_code": "Aktuell forskning inom datanätverk (DVAE24)",
    "positive_summary": [
      "Course supervisor noted the course worked well based on class discussions."
    ],
    "critique_summary": [
      "Supervisor noted challenges with the Christmas break affecting project deadlines."
    ],
    "workload": "No student feedback available (mean 0.0).",
    "trend_over_time": "Stable progression across previous evaluation terms...",
    "reports_analyzed": [
      "HT-25 (KAU-47889)",
      "HT-24 (KAU-45494)"
    ]
  }
}
```

### Stream real-time updates (SSE)

```http
GET /api/v1/evaluations/jobs/job_a1b2c3d4e5f6/stream
X-API-Key: dev-secret-key-12345
```

Streams real-time events:
```text
event: status
data: {"job_id": "job_a1b2c3d4e5f6", "status": "PENDING"}

event: update
data: {"status": "PROCESSING", "message": "Fetching evaluations for DVAE24..."}

event: update
data: {"status": "COMPLETED", "message": "Evaluation summary completed successfully."}
```

### Upload custom PDFs

```http
POST /api/v1/evaluations/jobs/upload
Content-Type: multipart/form-data
X-API-Key: dev-secret-key-12345

files: [binary PDF files]
output_language: "English"
```

---

## Running Tests

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## Docker

```powershell
docker compose up -d --build
docker compose logs -f
```
