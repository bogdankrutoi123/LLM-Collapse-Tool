from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterator

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "functional-test-secret-key-do-not-use")
os.environ.setdefault("PUBLIC_REGISTRATION_ENABLED", "True")
os.environ.setdefault("BOOTSTRAP_ADMIN_TOKEN", "functional-bootstrap-token")
os.environ.setdefault("ENFORCE_HTTPS", "False")
os.environ.setdefault("ENCRYPT_DATA", "False")
os.environ.setdefault("DEBUG", "False")

THIS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = THIS_DIR.parent.resolve()
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import session as db_session_module
from app.db.session import Base, get_db
from app.main import app
from app.models.database import UserRole
from app.schemas.schemas import UserCreate
from app.services.user_service import UserService

COLLAPSE_DIR = (BACKEND_DIR.parent / "notebooks" / "collapse_models").resolve()
MODELS_ROOT = COLLAPSE_DIR / "models"


def _setup_app() -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_session_module.engine = engine
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_session_module.SessionLocal = session_factory

    def _override_get_db() -> Iterator:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db

    db = session_factory()
    UserService.create_user(
        db,
        UserCreate(
            email="admin@functional-test.example.com",
            username="admin",
            full_name="Functional Admin",
            password="testpassword123",
            role=UserRole.ADMIN,
        ),
    )
    db.close()
    return TestClient(app)


def _login(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "testpassword123"},
    )
    resp.raise_for_status()


def _make_version_pointing_at_local_checkpoint(
    client: TestClient, checkpoint: Path
) -> int:
    model = client.post(
        "/api/v1/models/",
        json={
            "name": "distilgpt2-collapse-functional",
            "description": "real local checkpoint for E2E coverage",
            "source": "hf:distilbert/distilgpt2",
        },
    )
    model.raise_for_status()

    version = client.post(
        f"/api/v1/models/{model.json()['id']}/versions",
        json={
            "model_id": model.json()["id"],
            "version": "gen0-functional",
            "model_metadata": {"hf_model_id": "distilbert/distilgpt2"},
            "weights_path": str(checkpoint),
        },
    )
    version.raise_for_status()
    return version.json()["id"]


def _create_prompt(client: TestClient, version_id: int, text: str) -> int:
    resp = client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version_id, "input_text": text},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _generate(
    client: TestClient,
    prompt_id: int,
    *,
    max_new_tokens: int,
    temperature: float,
) -> dict:
    resp = client.post(
        f"/api/v1/prompts/{prompt_id}/generate",
        json={
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
        },
    )
    resp.raise_for_status()
    return resp.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gen",
        type=int,
        default=0,
        choices=[0, 1, 2, 3, 4, 5],
        help="which collapse checkpoint to point the model version at",
    )
    parser.add_argument("--max-new-tokens", type=int, default=24)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument(
        "--prompt",
        default="Once upon a time,",
        help="seed text fed to the model",
    )
    args = parser.parse_args(argv)

    checkpoint = MODELS_ROOT / f"gen_{args.gen}"
    if not checkpoint.is_dir():
        print(f"[FAIL] missing checkpoint dir: {checkpoint}", file=sys.stderr)
        return 2
    if not (checkpoint / "config.json").exists():
        print(f"[FAIL] checkpoint at {checkpoint} has no config.json", file=sys.stderr)
        return 2

    print(f"[INFO] using checkpoint {checkpoint}")
    print(f"[INFO] prompt: {args.prompt!r}")
    print(f"[INFO] max_new_tokens={args.max_new_tokens} temperature={args.temperature}")

    client = _setup_app()
    _login(client)
    version_id = _make_version_pointing_at_local_checkpoint(client, checkpoint)
    prompt_id = _create_prompt(client, version_id, args.prompt)
    result = _generate(
        client, prompt_id,
        max_new_tokens=args.max_new_tokens, temperature=args.temperature,
    )

    output_text: str = result.get("output_text") or ""
    output_length = result.get("output_length")
    gen_ms = result.get("generation_time_ms")

    print()
    print("=" * 72)
    print(f"output_text       : {output_text!r}")
    print(f"output_length     : {output_length}")
    print(f"generation_time_ms: {gen_ms}")
    print("=" * 72)

    failures: list[str] = []
    if not output_text or len(output_text.strip()) == 0:
        failures.append("output_text is empty")
    if not isinstance(output_length, int) or output_length <= 0:
        failures.append(f"output_length not positive: {output_length!r}")
    if gen_ms is None or gen_ms <= 0:
        failures.append(f"generation_time_ms not positive: {gen_ms!r}")

    if failures:
        print()
        print("[FAIL] functional generate test failed:")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("[OK] real-checkpoint generate endpoint test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
