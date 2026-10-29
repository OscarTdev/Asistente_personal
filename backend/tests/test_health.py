"""GET /health must answer 200 with a static payload."""


async def test_health_returns_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert data["database"] == "ok"
    # Redis might not be available in all test environments
