"""The first real run of the API: every read endpoint answers, using seeded data."""
from __future__ import annotations


def test_health(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200


def test_sixteen_agents_are_seeded_and_public(client) -> None:
    response = client.get("/api/public/agents")
    assert response.status_code == 200, response.text
    assert len(response.json()["agents"]) == 16


def test_owner_can_read_every_admin_page(owner) -> None:
    for path in (
        "overview",
        "system",
        "settings",
        "agents",
        "knowledge-bases",
        "conversations",
        "escalations",
        "audit-log",
        "users",
        "latency",
    ):
        response = owner.get(f"/api/admin/{path}")
        assert response.status_code == 200, f"{path}: {response.text}"


def test_admin_needs_a_session(client) -> None:
    assert client.get("/api/admin/overview").status_code == 401
