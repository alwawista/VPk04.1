from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    @contextmanager
    def _factory(**overrides: str) -> Iterator[TestClient]:
        env = {
            "API_KEYS": "test-key",
            "REQUIRE_API_AUTH": "false",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'triage.db'}",
            "REDIS_URL": "",
            "LLM_PROVIDER": "mock",
            "LLM_TIMEOUT_SECONDS": "0.05",
            "LLM_DAILY_BUDGET_USD": "5",
            "RATE_LIMIT_API_KEY_PER_MINUTE": "100",
            "RATE_LIMIT_IP_PER_MINUTE": "100",
            "RATE_LIMIT_CLIENT_PER_MINUTE": "100",
            "RATE_LIMIT_GLOBAL_PER_MINUTE": "1000",
            "SPOOL_PATH": str(tmp_path / "spool" / "emergency.jsonl"),
        }
        env.update(overrides)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        app = create_app()
        with TestClient(app) as test_client:
            yield test_client

    return _factory


@pytest.fixture
def client(client_factory) -> Iterator[TestClient]:
    with client_factory() as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-key"}


def payload(**overrides):
    data = {
        "text": "Feedback form is not working",
        "channel": "form",
        "client_id": "client-1",
    }
    data.update(overrides)
    return data
