"""Integration test: requires the database to be running (`docker compose up -d db`)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_db_and_pgvector():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["pgvector"]  # e.g. "0.8.0"
