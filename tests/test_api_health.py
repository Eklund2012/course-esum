def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "course-esum"}

def test_readyz(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["database"] == "connected"
    assert "gemini_ai" in data

def test_openapi_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "paths" in schema
    assert "/api/v1/evaluations/jobs/fetch" in schema["paths"]
    assert "/api/v1/evaluations/jobs/upload" in schema["paths"]
