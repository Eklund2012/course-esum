def test_missing_api_key_returns_401(client):
    response = client.get("/api/v1/evaluations/history")
    assert response.status_code == 401
    assert "Missing 'X-API-Key'" in response.json()["detail"]

def test_invalid_api_key_returns_403(client):
    response = client.get("/api/v1/evaluations/history", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 403
    assert "Invalid API key" in response.json()["detail"]

def test_valid_api_key_authorized(client, auth_headers):
    response = client.get("/api/v1/evaluations/history", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
