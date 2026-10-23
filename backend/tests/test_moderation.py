"""Moderation permissions, content actions, suspensions and the audit trail."""

from __future__ import annotations

from app.models.enums import ReportStatus
from app.models.moderation import AuditLog, ModerationAction
from app.models.user import User
from tests.conftest import login, make_video


def _report(client, headers, video) -> dict:
    response = client.post(
        "/api/v1/reports",
        json={"target_type": "video", "target_id": str(video.id), "reason": "harassment"},
        headers=headers,
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


def test_regular_users_cannot_reach_moderation_tools(api):
    client, db = api["client"], api["db"]
    video = make_video(db, api["creator"])
    _report(client, login(client, api["viewer"]), video)

    headers = login(client, api["viewer"])
    assert client.get("/api/v1/moderation/reports", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/stats", headers=headers).status_code == 403
    assert client.get("/api/v1/moderation/summary", headers=headers).status_code == 403


def test_moderator_resolves_report_and_removes_content(api):
    client, db = api["client"], api["db"]
    video = make_video(db, api["creator"])
    reporter_headers = login(client, api["viewer"])
    _report(client, reporter_headers, video)

    mod_headers = login(client, api["moderator"], api["passwords"]["moderator"])
    queue = client.get("/api/v1/moderation/reports", params={"status": "open"}, headers=mod_headers)
    assert queue.status_code == 200
    report = queue.json()["items"][0]
    assert report["target_preview"]["id"] == str(video.id)

    resolved = client.post(
        f"/api/v1/moderation/reports/{report['id']}/resolve",
        json={"status": "resolved", "action": "content_removed", "note": "Violates community rules"},
        headers=mod_headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == ReportStatus.resolved.value

    db.refresh(video)
    assert video.is_removed is True
    assert db.query(ModerationAction).count() == 1

    hidden = client.get(f"/api/v1/videos/{video.id}")
    assert hidden.status_code == 404

    restored = client.post(
        "/api/v1/moderation/content-action",
        json={"target_type": "video", "target_id": str(video.id), "reason": "appeal accepted", "restore": True},
        headers=mod_headers,
    )
    assert restored.status_code == 200
    db.refresh(video)
    assert video.is_removed is False


def test_suspension_revokes_sessions_and_blocks_sign_in(api):
    client, db = api["client"], api["db"]
    victim = api["viewer"]
    victim_password = api["passwords"]["viewer"]
    login(client, victim, victim_password)

    mod_headers = login(client, api["moderator"], api["passwords"]["moderator"])
    suspended = client.post(
        f"/api/v1/moderation/users/{victim.id}/suspend",
        json={"user_id": str(victim.id), "reason": "Repeated spam"},
        headers=mod_headers,
    )
    assert suspended.status_code == 200, suspended.text

    db.refresh(victim)
    assert victim.is_suspended is True

    blocked = client.post("/api/v1/auth/login", json={"email": victim.email, "password": victim_password})
    assert blocked.status_code == 403

    reinstated = client.post(f"/api/v1/moderation/users/{victim.id}/reinstate", headers=mod_headers)
    assert reinstated.status_code == 200
    db.refresh(victim)
    assert victim.is_suspended is False


def test_moderator_cannot_suspend_an_admin(api):
    client = api["client"]
    mod_headers = login(client, api["moderator"], api["passwords"]["moderator"])
    response = client.post(
        f"/api/v1/moderation/users/{api['admin'].id}/suspend",
        json={"user_id": str(api["admin"].id), "reason": "Test"},
        headers=mod_headers,
    )
    assert response.status_code in {400, 403}


def test_admin_role_change_and_audit_log(api):
    client, db = api["client"], api["db"]
    admin_headers = login(client, api["admin"], api["passwords"]["admin"])

    promoted = client.patch(
        f"/api/v1/admin/users/{api['viewer'].id}/role", params={"role": "creator"}, headers=admin_headers
    )
    assert promoted.status_code == 200, promoted.text
    db.refresh(api["viewer"])
    assert api["viewer"].role.value == "creator"

    log = client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    assert log.status_code == 200
    actions = [item["action"] for item in log.json()["items"]]
    assert "role_changed" in actions
    assert db.query(AuditLog).filter(AuditLog.action == "role_changed").count() == 1

    stats = client.get("/api/v1/admin/stats", headers=admin_headers)
    assert stats.status_code == 200
    assert stats.json()["users"]["total"] >= 4


def test_categories_can_be_managed(api):
    client = api["client"]
    admin_headers = login(client, api["admin"], api["passwords"]["admin"])

    created = client.post(
        "/api/v1/admin/categories",
        json={"slug": "street_food", "label": "Street food", "kind": "video"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text

    duplicate = client.post(
        "/api/v1/admin/categories",
        json={"slug": "street_food", "label": "Street food", "kind": "video"},
        headers=admin_headers,
    )
    assert duplicate.status_code == 409

    public = client.get("/api/v1/categories")
    assert any(item["slug"] == "street_food" for item in public.json()["items"])