from __future__ import annotations

import json
import os
import statistics
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("PUBLIC_REGISTRATION_ENABLED", "True")
os.environ.setdefault("BOOTSTRAP_ADMIN_TOKEN", "test-bootstrap-token")
os.environ.setdefault("ENFORCE_HTTPS", "False")
os.environ.setdefault("ENCRYPT_DATA", "False")
os.environ.setdefault("DEBUG", "False")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import session as db_session_module
from app.db.session import Base, get_db
from app.main import app
from app.models.database import User, UserRole
from app.services.user_service import UserService
from app.schemas.schemas import UserCreate

REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)


@pytest.fixture(scope="session")
def engine():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_session_module.engine = test_engine
    Base.metadata.create_all(bind=test_engine)
    return test_engine


@pytest.fixture(scope="session")
def session_factory(engine):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_session_module.SessionLocal = factory
    return factory


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _truncate_tables(engine):
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.exec_driver_sql(f"DELETE FROM {table.name}")


@pytest.fixture()
def app_with_db(session_factory):
    def _override_get_db() -> Iterator:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield app
    app.dependency_overrides.pop(get_db, None)


class _StubTokenizer:
    eos_token_id = 0

    def __call__(self, text: str, return_tensors: str | None = None):
        import torch
        ids = torch.tensor([[1, 2, 3, 4, 5]])
        return {"input_ids": ids, "attention_mask": torch.ones_like(ids)}

    def tokenize(self, text: str) -> List[str]:
        return text.split()

    def convert_ids_to_tokens(self, ids):
        return [f"tok_{i}" for i in ids]

    def convert_tokens_to_string(self, tokens):
        return " ".join(str(t) for t in tokens)

    def decode(self, ids, skip_special_tokens: bool = True) -> str:
        return "stub-generated text"


class _StubModel:
    def eval(self):
        return self

    def generate(self, **kwargs):
        import torch
        input_ids = kwargs["input_ids"]
        max_new = int(kwargs.get("max_new_tokens", 4))
        new_tokens = torch.arange(10, 10 + max_new).unsqueeze(0)
        full = torch.cat([input_ids, new_tokens], dim=1)

        class _Out:
            sequences = full
            scores = [torch.zeros((1, 32)) for _ in range(max_new)]

        return _Out()

    def __call__(self, *args, **kwargs):
        import torch

        class _Result:
            loss = torch.tensor(2.0)

        return _Result()


@pytest.fixture(autouse=True)
def stub_hf_loader(monkeypatch):
    def _fake_loader(model_id, local_path=None):
        return _StubTokenizer(), _StubModel()

    monkeypatch.setattr("app.services.wikitext_service._load_model_and_tokenizer", _fake_loader)
    monkeypatch.setattr("app.api.routes.prompts._load_model_and_tokenizer", _fake_loader)
    yield


class LatencyTracker:
    def __init__(self) -> None:
        self.samples: Dict[str, List[float]] = defaultdict(list)
        self.errors: Dict[str, int] = defaultdict(int)
        self.requests: Dict[str, int] = defaultdict(int)
        self.session_started = time.perf_counter()

    @contextmanager
    def measure(self, label: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.samples[label].append(elapsed_ms)
            self.requests[label] += 1

    def record(self, label: str, response) -> None:
        if response.status_code >= 500:
            self.errors[label] += 1

    def summary(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for label, values in self.samples.items():
            if not values:
                continue
            sorted_v = sorted(values)
            out[label] = {
                "n": len(sorted_v),
                "mean_ms": round(statistics.fmean(sorted_v), 3),
                "p50_ms": round(_percentile(sorted_v, 50), 3),
                "p95_ms": round(_percentile(sorted_v, 95), 3),
                "p99_ms": round(_percentile(sorted_v, 99), 3),
                "max_ms": round(max(sorted_v), 3),
                "errors_5xx": self.errors.get(label, 0),
            }
        return out


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * (pct / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


@pytest.fixture(scope="session")
def latency() -> LatencyTracker:
    return LatencyTracker()


@pytest.fixture()
def client(app_with_db, latency) -> Iterator[Tuple[TestClient, LatencyTracker]]:
    real_client = TestClient(app_with_db)
    original_request = real_client.request

    def _wrapped_request(method, url, *args, **kwargs):
        label = f"{method.upper()} {url.split('?')[0]}"
        with latency.measure(label):
            response = original_request(method, url, *args, **kwargs)
        latency.record(label, response)
        return response

    real_client.request = _wrapped_request  # type: ignore[assignment]
    try:
        yield real_client, latency
    finally:
        real_client.close()


@pytest.fixture()
def make_user(db):
    def _make(
        username: str = "tester",
        email: str | None = None,
        password: str = "testpassword123",
        role: UserRole = UserRole.OPERATOR,
        full_name: str = "Test User",
    ) -> User:
        payload = UserCreate(
            email=email or f"{username}@example.com",
            username=username,
            full_name=full_name,
            password=password,
            role=role,
        )
        return UserService.create_user(db, payload)

    return _make


@pytest.fixture()
def login_as(client, make_user):
    real_client, _ = client

    def _login(role: UserRole = UserRole.ADMIN, username: str | None = None):
        username = username or {
            UserRole.ADMIN: "admin",
            UserRole.MODEL_ENGINEER: "engineer",
            UserRole.OPERATOR: "operator",
        }[role]
        password = "testpassword123"
        make_user(username=username, role=role, password=password)
        resp = real_client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _login


def pytest_sessionfinish(session, exitstatus):
    tracker: LatencyTracker | None = getattr(session.config, "_latency_tracker", None)
    if tracker is None:
        return
    summary = tracker.summary()
    duration_s = round(time.perf_counter() - tracker.session_started, 3)
    total_requests = sum(tracker.requests.values())
    total_errors = sum(tracker.errors.values())
    error_rate = (total_errors / total_requests) if total_requests else 0.0
    payload = {
        "session_seconds": duration_s,
        "total_requests": total_requests,
        "total_5xx": total_errors,
        "error_rate": round(error_rate, 4),
        "throughput_rps": round(total_requests / duration_s, 3) if duration_s else 0.0,
        "endpoints": summary,
    }
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "metrics.json").write_text(json.dumps(payload, indent=2))
    (REPORT_DIR / "metrics.md").write_text(_markdown_report(payload))


def _markdown_report(payload: dict) -> str:
    rows = ["# API performance metrics", ""]
    rows.append(f"{payload['session_seconds']} seconds elapsed")
    rows.append(f"{payload['total_requests']} total requests")
    rows.append(f"{payload['total_5xx']} {payload['error_rate']*100:.2f}% 5xx errors")
    rows.append(f"{payload['throughput_rps']} req/s**")
    rows.append("")

    for label, stats in sorted(payload["endpoints"].items()):
        rows.append(
            f"| `{label}` | {stats['n']} | {stats['mean_ms']} | {stats['p50_ms']} "
            f"| {stats['p95_ms']} | {stats['p99_ms']} | {stats['max_ms']} | {stats['errors_5xx']} |"
        )
    rows.append("")
    return "\n".join(rows)


@pytest.fixture(scope="session", autouse=True)
def _store_tracker_on_config(request, latency):
    request.config._latency_tracker = latency
    yield
