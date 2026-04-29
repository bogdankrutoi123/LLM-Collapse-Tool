from datetime import datetime

from app.models.database import Notification, NotificationStatus, UserRole


def _seed_notification(db, *, severity: str = "warning", status: str = "pending") -> Notification:
    notif = Notification(
        title="Test alert",
        message="metric exceeded threshold",
        severity=severity,
        status=NotificationStatus(status),
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def test_list_notifications_filtered_by_status(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    _seed_notification(db, status="pending")
    _seed_notification(db, status="closed")
    resp = real_client.get("/api/v1/notifications/?status=pending")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"


def test_acknowledge_notification(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    notif = _seed_notification(db)
    resp = real_client.put(f"/api/v1/notifications/{notif.id}",
                           json={"status": "acknowledged", "response_comment": "investigating"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "acknowledged"
    assert body["response_comment"] == "investigating"


def test_close_notification(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    notif = _seed_notification(db, status="acknowledged")
    resp = real_client.put(f"/api/v1/notifications/{notif.id}", json={"status": "closed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


def test_notification_404(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.get("/api/v1/notifications/9999")
    assert resp.status_code == 404
