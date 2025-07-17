def test_health(client):
    r = client.get("/api/v1/health/")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"

def test_upload_document(client):
    # You'd add code to test document upload endpoint
    pass

def test_query_process(client):
    # You'd add code to test the query processing endpoint
    pass
