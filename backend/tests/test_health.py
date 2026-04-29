def test_root_endpoint(client):
    real_client, _ = client
    resp = real_client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert "name" in body and "version" in body


def test_health_endpoint(client):
    real_client, _ = client
    resp = real_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}
