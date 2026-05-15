import json

import pytest

from app.core.config import get_settings
from app.models.database import UserRole


@pytest.fixture()
def isolated_export_dir(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "EXPORT_DIR", str(tmp_path))
    yield tmp_path


def test_create_backup_requires_admin(client, login_as, isolated_export_dir):
    real_client, _ = client
    login_as(role=UserRole.OPERATOR)
    resp = real_client.post("/api/v1/backup/create")
    assert resp.status_code == 403


def test_create_backup_writes_file(client, login_as, isolated_export_dir):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    real_client.post(
        "/api/v1/models/",
        json={"name": "backup-source", "source": "hf:test/test"},
    )

    resp = real_client.post("/api/v1/backup/create")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["filename"].startswith("backup_")
    assert body["filename"].endswith(".json")

    backup_path = isolated_export_dir / "backups" / body["filename"]
    assert backup_path.exists()
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    assert "users" in payload and "models" in payload
    assert any(m.get("name") == "backup-source" for m in payload["models"])


def test_list_backups_returns_recent_first(client, login_as, isolated_export_dir):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    backup_dir = isolated_export_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "backup_20240101_000000.json").write_text("{}")
    (backup_dir / "backup_20250101_000000.json").write_text("{}")
    (backup_dir / "irrelevant.json").write_text("{}")

    resp = real_client.get("/api/v1/backup/list")
    assert resp.status_code == 200
    listing = resp.json()
    assert listing == [
        "backup_20250101_000000.json",
        "backup_20240101_000000.json",
    ]


def test_restore_missing_file_returns_404(client, login_as, isolated_export_dir):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/backup/restore",
        json={"filename": "does-not-exist.json", "replace": False},
    )
    assert resp.status_code == 404


def test_restore_loads_serializable_payload(client, login_as, isolated_export_dir):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    backup_dir = isolated_export_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "models": [
            {"id": 991, "name": "restored-model", "description": "from-backup"},
        ],
    }
    fname = "backup_19990101_000000.json"
    (backup_dir / fname).write_text(json.dumps(payload), encoding="utf-8")

    resp = real_client.post(
        "/api/v1/backup/restore",
        json={"filename": fname, "replace": False},
    )
    assert resp.status_code == 200, resp.text
    listing = real_client.get("/api/v1/models/").json()
    assert any(m["name"] == "restored-model" for m in listing)


def test_restore_with_replace_wipes_tables(client, login_as, isolated_export_dir):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    real_client.post(
        "/api/v1/models/",
        json={"name": "to-be-wiped", "source": "hf:wipe/me"},
    )

    backup_dir = isolated_export_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    fname = "backup_empty.json"
    (backup_dir / fname).write_text("{}", encoding="utf-8")

    resp = real_client.post(
        "/api/v1/backup/restore",
        json={"filename": fname, "replace": True},
    )
    assert resp.status_code == 200, resp.text
