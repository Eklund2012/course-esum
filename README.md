# Course Evaluation Summarizer Service (`course-esum`)

An enterprise-ready, asynchronous microservice that analyzes and summarizes university course evaluation reports (*kursutvärderingsanalyser*) using **Google Gemini 2.5 Flash** and **FastAPI**.

---

## Features

- **Automated University Fetching**: Enter a Karlstad University course code (e.g. `DVAE24`, `DVAE23`, `ISGB11`) to automatically scrape, download, and analyze official PDF evaluation reports in-memory without manual file uploads.
- **Multimodal PDF Ingestion**: Directly streams PDF byte documents into Gemini 2.5 Flash, preserving multi-column layouts, score distributions, and tables without OCR degradation.
- **Asynchronous 202 Accepted Architecture**: Decouples client HTTP connections from long-running LLM inference via background task execution.
- **Real-Time SSE Streaming**: Clients can subscribe to `GET /api/v1/evaluations/jobs/{job_id}/stream` for instant push notifications as evaluations process.
- **Pluggable Provider Architecture**: Clean `CourseEvaluationProvider` abstraction supporting Karlstad University (`KarlstadUniversityProvider`) and mock data (`MockCourseProvider`), easily extensible to other institutions (e.g., Canvas LMS, EvaSys, Ladok).
- **Persistent State & History**: SQLModel (SQLAlchemy) database tracking jobs, courses, positive/critique summaries, workloads, and multi-year trends.
- **Security & Rate Limiting**: `X-API-Key` authentication header and request rate limiting (`slowapi`).

---

## Quick Start

### 1. Configure Environment

Ensure your `.env` contains your Gemini API key:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
API_KEY=dev-secret-key-12345
DATABASE_URL=sqlite:///./course_esum.db
APP_ENV=development
```

### 2. Run the Service Locally

Activate your virtual environment and start the Uvicorn server:

```powershell
# Set PYTHONPATH to include src
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn course_esum.main:app --reload --port 8000
```

The interactive API documentation is available at:
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## API Reference

All requests require the `X-API-Key` header (default in development: `dev-secret-key-12345`).

### 1. Submit Evaluation by Course Code (Karlstad University)

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

### 2. Poll Job Status & Summary

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

### 3. Stream Real-Time Updates (SSE)

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

### 4. Upload Custom PDFs

```http
POST /api/v1/evaluations/jobs/upload
Content-Type: multipart/form-data
X-API-Key: dev-secret-key-12345

files: [binary PDF files]
output_language: "English"
```

---

## Running Automated Tests

Run the full automated test suite with pytest:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## Docker Deployment

```powershell
# Build and run with Docker Compose
docker compose up -d --build

# Inspect logs
docker compose logs -f
```
