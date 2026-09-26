import io
from unittest.mock import patch
from course_esum.schemas.evaluation import CourseEvaluationSummary

MOCK_SUMMARY = CourseEvaluationSummary(
    course_name_and_code="Test Course (TEST101)",
    positive_summary=["Great interactive lectures", "Helpful assignments"],
    critique_summary=["Workload was slightly uneven"],
    workload="appropriate",
    trend_over_time="Consistently high student engagement over past 2 terms"
)

def test_create_fetch_job(client, auth_headers):
    # Enqueue job
    response = client.post(
        "/api/v1/evaluations/jobs/fetch",
        json={"course_code": "TEST101", "output_language": "English", "max_reports": 2},
        headers=auth_headers
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"
    assert data["course_code"] == "TEST101"
    assert "status" in data["links"]
    assert "stream" in data["links"]

    # Poll status immediately
    job_id = data["job_id"]
    get_res = client.get(f"/api/v1/evaluations/jobs/{job_id}", headers=auth_headers)
    assert get_res.status_code == 200
    job_data = get_res.json()
    assert job_data["job_id"] == job_id
    assert job_data["course_code"] == "TEST101"

def test_create_upload_job_validation(client, auth_headers):
    # Fail if not a PDF
    response = client.post(
        "/api/v1/evaluations/jobs/upload",
        files=[("files", ("test.txt", b"not a pdf", "text/plain"))],
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "is not a PDF" in response.json()["detail"]

def test_create_upload_job_success(client, auth_headers):
    response = client.post(
        "/api/v1/evaluations/jobs/upload",
        files=[("files", ("eval_2024.pdf", b"%PDF-1.4 dummy pdf bytes", "application/pdf"))],
        data={"output_language": "Swedish"},
        headers=auth_headers
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["input_type"] == "FILE_UPLOAD"

def test_get_nonexistent_job(client, auth_headers):
    response = client.get("/api/v1/evaluations/jobs/non_existent_id", headers=auth_headers)
    assert response.status_code == 404
