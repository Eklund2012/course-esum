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


def test_create_upload_job_wrong_mime_type(client, auth_headers):
    """Uploading a non-PDF MIME type must be rejected with 400."""
    response = client.post(
        "/api/v1/evaluations/jobs/upload",
        files=[("files", ("test.txt", b"not a pdf", "text/plain"))],
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "unsupported type" in response.json()["detail"]


def test_create_upload_job_renamed_non_pdf(client, auth_headers):
    """A .pdf filename with non-PDF content (wrong magic bytes) must be rejected."""
    response = client.post(
        "/api/v1/evaluations/jobs/upload",
        # Correct MIME type declared but content is not a real PDF
        files=[("files", ("fake.pdf", b"This is plaintext, not a PDF", "application/pdf"))],
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "does not appear to be a valid PDF" in response.json()["detail"]


def test_create_upload_job_empty_file(client, auth_headers):
    """Uploading an empty file must be rejected with 400."""
    response = client.post(
        "/api/v1/evaluations/jobs/upload",
        files=[("files", ("empty.pdf", b"", "application/pdf"))],
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "is empty" in response.json()["detail"]


def test_create_upload_job_size_limit(client, auth_headers):
    """Files exceeding MAX_UPLOAD_SIZE_MB must be rejected with 413."""
    # Patch the limit to 1 byte to trigger the check without allocating real memory
    from course_esum.config import get_settings
    with patch.object(get_settings(), "MAX_UPLOAD_SIZE_MB", 0):  # 0 MB => 0 bytes limit
        response = client.post(
            "/api/v1/evaluations/jobs/upload",
            files=[("files", ("big.pdf", b"%PDF-1.4 some content", "application/pdf"))],
            headers=auth_headers
        )
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]


def test_create_upload_job_success(client, auth_headers):
    # Minimal valid PDF bytes (well-formed enough to pass pypdf structural check)
    # We use a real minimal PDF structure so PdfReader doesn't raise PdfReadError.
    min_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
    )
    response = client.post(
        "/api/v1/evaluations/jobs/upload",
        files=[("files", ("eval_2024.pdf", min_pdf, "application/pdf"))],
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
