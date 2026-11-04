"""Shared fixtures. The `light` runtime needs no model files, so these run anywhere in seconds."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.main import create_app  # noqa: E402

OWNER = {"email": "owner@example.test", "password": "Fixture-Pass-2026!"}


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        models_dir=tmp_path / "no-models",
        admin_email=OWNER["email"],
        admin_password=OWNER["password"],
        llm_manage_process=False,
        rate_limit_per_minute=100000,
    )


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings, light=True)
    with TestClient(app, base_url="http://localhost:8000") as test_client:
        test_client.headers["origin"] = "http://localhost:8000"
        yield test_client


@pytest.fixture()
def owner(client: TestClient) -> TestClient:
    response = client.post("/api/auth/login", json=OWNER)
    assert response.status_code == 200, response.text
    return client
