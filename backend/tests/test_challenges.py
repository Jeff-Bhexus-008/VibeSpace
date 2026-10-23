"""Battle lifecycle, deadlines, vote eligibility and official results."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.challenge import Challenge, ChallengeEntry, Vote
from app.models.enums import ChallengeStatus, EntryStatus, ReportTarget
from tests.conftest import login, make_media, make_user, make_video


def _create_battle(client, headers, opponent_username: str | None = None, **overrides) -> dict:
    payload = {
        "title": "Dance-off Friday",
        "description": "Show your best move",
        "category": "dance",
        "format": "open_challenge",
        "publish": True,
        "deadline_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "voting_ends_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
    }
    if opponent_username:
        payload["format"] = "head_to_head"
        payload["opponent_username"] = opponent_username
    payload.update(overrides)
    return client.post("/api/v1/challenges", json=payload, headers=headers)


def test_create_battle_requires_verified_account_and_valid_schedule(api):
    client, db = api["client"], api["db"]
    creator = api["creator"]
    headers = login(client, creator)

    created = _create_battle(client, headers)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "open"
    assert created.json()["is_owner"] is True

    bad_schedule = _create_battle(
        client,
        headers,
        starts_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        deadline_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    assert bad_schedule.status_code == 422

    unverified, password = make_user(db, verified=False)
    unverified_headers = login(client, unverified, password)
    assert _create_battle(client, unverified_headers).status_code == 400


def test_head_to_head_needs_an_opponent(api):
    client = api["client"]
    headers = login(client, api["creator"])
    response = client.post(
        "/api/v1/challenges",
        json={"title": "Code duel", "category": "coding", "format": "head_to_head"},
        headers=headers,
    )
    assert response.status_code == 422


def test_entry_submission_respects_deadline_and_limits(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    creator_headers = login(client, creator)
    viewer_headers = login(client, viewer)

    battle = _create_battle(client, creator_headers).json()
    asset = make_media(db, viewer)

    submitted = client.post(
        f"/api/v1/challenges/{battle['id']}/entries",
        json={"media_asset_id": str(asset.id), "title": "My entry"},
        headers=viewer_headers,
    )
    assert submitted.status_code == 201, submitted.text
    entry_id = submitted.json()["id"]

    second = client.post(
        f"/api/v1/challenges/{battle['id']}/entries",
        json={"media_asset_id": str(asset.id), "title": "Second entry"},
        headers=viewer_headers,
    )
    assert second.status_code == 409  # one entry per user by default

    # Closed deadline: no further entries are accepted.
    deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.execute(
        Challenge.__table__.update().where(Challenge.id == battle["id"]).values(deadline_at=deadline)
    )
    db.commit()

    other, password = make_user(db)
    other_headers = login(client, other, password)
    other_asset = make_media(db, other)
    late = client.post(
        f"/api/v1/challenges/{battle['id']}/entries",
        json={"media_asset_id": str(other_asset.id), "title": "Too late"},
        headers=other_headers,
    )
    assert late.status_code == 409

    db.refresh(db.get(ChallengeEntry, entry_id))
    assert db.get(ChallengeEntry, entry_id).status == EntryStatus.submitted


def test_vote_eligibility_duplicates_and_organiser_restriction(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    creator_headers = login(client, creator)
    viewer_headers = login(client, viewer)

    battle = _create_battle(client, creator_headers).json()
    viewer_asset = make_media(db, viewer)
    entry = client.post(
        f"/api/v1/challenges/{battle['id']}/entries",
        json={"media_asset_id": str(viewer_asset.id), "title": "Entry one"},
        headers=viewer_headers,
    ).json()

    organiser_vote = client.post(
        f"/api/v1/challenges/{battle['id']}/vote", json={"entry_id": entry["id"]}, headers=creator_headers
    )
    assert organiser_vote.status_code == 409

    voter, password = make_user(db)
    voter_headers = login(client, voter, password)

    first = client.post(
        f"/api/v1/challenges/{battle['id']}/vote", json={"entry_id": entry["id"]}, headers=voter_headers
    )
    assert first.status_code == 200, first.text

    duplicate = client.post(
        f"/api/v1/challenges/{battle['id']}/vote", json={"entry_id": entry["id"]}, headers=voter_headers
    )
    assert duplicate.status_code == 409
    assert db.query(Vote).filter(Vote.voter_id == voter.id).count() == 1

    # Votes closed: the same voter cannot vote in another battle after voting ends.
    db.execute(
        Challenge.__table__.update()
        .where(Challenge.id == battle["id"])
        .values(status=ChallengeStatus.completed)
    )
    db.commit()
    closed = client.post(
        f"/api/v1/challenges/{battle['id']}/vote",
        json={"entry_id": entry["id"]},
        headers=voter_headers,
    )
    assert closed.status_code == 400


def test_standings_provisional_then_final_and_frozen(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    creator_headers = login(client, creator)
    viewer_headers = login(client, viewer)

    battle = _create_battle(client, creator_headers).json()
    entry = client.post(
        f"/api/v1/challenges/{battle['id']}/entries",
        json={"media_asset_id": str(make_media(db, viewer).id), "title": "Entry one"},
        headers=viewer_headers,
    ).json()

    provisional = client.get(f"/api/v1/challenges/{battle['id']}/standings")
    assert provisional.status_code == 200
    assert provisional.json()["is_final"] is False
    assert "Provisional" in (provisional.json()["note"] or "")

    voter, password = make_user(db)
    voter_headers = login(client, voter, password)
    client.post(
        f"/api/v1/challenges/{battle['id']}/vote", json={"entry_id": entry["id"]}, headers=voter_headers
    )

    # Only moderators can publish official results.
    forbidden = client.post(f"/api/v1/challenges/{battle['id']}/finalize", headers=creator_headers)
    assert forbidden.status_code == 403

    client.post(
        f"/api/v1/challenges/{battle['id']}/state", json={"status": "voting"}, headers=creator_headers
    )
    moderator_headers = login(client, api["moderator"], api["passwords"]["moderator"])
    finalised = client.post(f"/api/v1/challenges/{battle['id']}/finalize", headers=moderator_headers)
    assert finalised.status_code == 200, finalised.text
    body = finalised.json()
    assert body["is_final"] is True
    assert body["rows"][0]["vote_count"] == 1

    standings = client.get(f"/api/v1/challenges/{battle['id']}/standings").json()
    assert standings["is_final"] is True

    db.refresh(db.get(Challenge, battle["id"]))
    assert db.get(Challenge, battle["id"]).winner_entry_id is not None

    # Completed battles are frozen.
    frozen = client.post(
        f"/api/v1/challenges/{battle['id']}/state", json={"status": "cancelled"}, headers=moderator_headers
    )
    assert frozen.status_code in {400, 409}


def test_illegal_state_transition_is_rejected(api):
    client = api["client"]
    headers = login(client, api["creator"])
    battle = _create_battle(client, headers).json()

    skipped = client.post(
        f"/api/v1/challenges/{battle['id']}/state", json={"status": "completed"}, headers=headers
    )
    assert skipped.status_code == 400  # must go through finalisation

    allowed = client.post(
        f"/api/v1/challenges/{battle['id']}/state", json={"status": "voting"}, headers=headers
    )
    assert allowed.status_code == 200
    assert "completed" in [state for state in allowed.json()["allowed_next"]]


def test_disqualification_removes_entry_from_standings(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    creator_headers = login(client, creator)
    viewer_headers = login(client, viewer)

    battle = _create_battle(client, creator_headers).json()
    entry = client.post(
        f"/api/v1/challenges/{battle['id']}/entries",
        json={"media_asset_id": str(make_media(db, viewer).id), "title": "Entry one"},
        headers=viewer_headers,
    ).json()

    moderator_headers = login(client, api["moderator"], api["passwords"]["moderator"])
    disqualified = client.post(
        f"/api/v1/challenges/{battle['id']}/entries/{entry['id']}/disqualify",
        params={"reason": "Video was not an original performance"},
        headers=moderator_headers,
    )
    assert disqualified.status_code == 200, disqualified.text
    assert disqualified.json()["status"] == EntryStatus.disqualified.value

    standings = client.get(f"/api/v1/challenges/{battle['id']}/standings").json()
    assert standings["rows"] == []


def test_only_participants_can_see_private_battles_and_history_is_audited(api):
    client, db = api["client"], api["db"]
    creator = api["creator"]
    creator_headers = login(client, creator)
    battle = _create_battle(client, creator_headers, is_public=False).json()

    outsider, password = make_user(db)
    outsider_headers = login(client, outsider, password)
    assert client.get(f"/api/v1/challenges/{battle['id']}", headers=outsider_headers).status_code == 403

    history = client.get(f"/api/v1/challenges/{battle['id']}/events", headers=creator_headers)
    assert history.status_code == 200
    assert any(item["event_type"] == "challenge_created" for item in history.json()["items"])

    # Auditing is restricted to the organiser or staff.
    assert client.get(f"/api/v1/challenges/{battle['id']}/events", headers=outsider_headers).status_code == 403


def test_feed_ranking_endpoint_and_discovery(api):
    client, db = api["client"], api["db"]
    creator = api["creator"]
    make_video(db, creator, title="Ranked video")

    feed = client.get("/api/v1/feed", params={"mode": "for_you"})
    assert feed.status_code == 200
    assert len(feed.json()["items"]) >= 1

    trending = client.get("/api/v1/discovery/trending")
    assert trending.status_code == 200
    assert "videos" in trending.json()

    ranking = client.get("/api/v1/feed/ranking")
    assert ranking.json()["strategy"] == "engagement_recency_affinity"

    search = client.get("/api/v1/search", params={"q": "Ranked", "type": "videos"})
    assert search.status_code == 200
    assert "videos" in search.json()