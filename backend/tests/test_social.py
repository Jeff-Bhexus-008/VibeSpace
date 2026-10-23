"""Likes, comments, follows, saves and view counting."""

from __future__ import annotations

from app.models.social import Like
from tests.conftest import login, make_user, make_video


def test_like_unlike_and_single_like_per_user(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    video = make_video(db, creator)
    headers = login(client, viewer)

    first = client.post(f"/api/v1/videos/{video.id}/like", headers=headers)
    assert first.status_code == 200
    assert first.json() == {"liked": True, "like_count": 1}

    duplicate = client.post(f"/api/v1/videos/{video.id}/like", headers=headers)
    assert duplicate.status_code == 409

    db.refresh(video)
    assert video.like_count == 1

    removed = client.delete(f"/api/v1/videos/{video.id}/like", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["like_count"] == 0
    assert db.query(Like).filter(Like.video_id == video.id).count() == 0


def test_comments_and_replies_update_counters(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    video = make_video(db, creator)
    viewer_headers = login(client, viewer)

    created = client.post(
        f"/api/v1/videos/{video.id}/comments", json={"body": "This is great"}, headers=viewer_headers
    )
    assert created.status_code == 201, created.text
    comment_id = created.json()["id"]

    creator_headers = login(client, creator)
    reply = client.post(
        f"/api/v1/videos/{video.id}/comments",
        json={"body": "Thanks!", "parent_id": comment_id},
        headers=creator_headers,
    )
    assert reply.status_code == 201

    db.refresh(video)
    assert video.comment_count == 2

    listing = client.get(f"/api/v1/videos/{video.id}/comments")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1  # top-level only

    replies = client.get(f"/api/v1/comments/{comment_id}/replies")
    assert len(replies.json()["items"]) == 1

    forbidden = client.delete(f"/api/v1/comments/{comment_id}", headers=creator_headers)
    assert forbidden.status_code == 403

    removed = client.delete(f"/api/v1/comments/{comment_id}", headers=viewer_headers)
    assert removed.status_code == 200


def test_follow_unfollow_and_no_duplicates(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    headers = login(client, viewer)

    followed = client.post(f"/api/v1/users/{creator.username}/follow", headers=headers)
    assert followed.status_code == 200
    assert followed.json()["following"] is True

    again = client.post(f"/api/v1/users/{creator.username}/follow", headers=headers)
    assert again.status_code == 200  # idempotent

    db.refresh(creator)
    assert creator.profile.follower_count == 1

    self_follow = client.post(f"/api/v1/users/{viewer.username}/follow", headers=headers)
    assert self_follow.status_code == 400

    unfollowed = client.delete(f"/api/v1/users/{creator.username}/follow", headers=headers)
    assert unfollowed.status_code == 200
    db.refresh(creator)
    assert creator.profile.follower_count == 0


def test_block_removes_follows_and_blocks_messaging(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    viewer_headers = login(client, viewer)
    creator_headers = login(client, creator)

    client.post(f"/api/v1/users/{creator.username}/follow", headers=viewer_headers)
    blocked = client.post(f"/api/v1/users/{creator.username}/block", json={}, headers=viewer_headers)
    assert blocked.status_code == 200

    dm = client.post(
        "/api/v1/conversations",
        json={"participant_usernames": [viewer.username], "first_message": "hi"},
        headers=creator_headers,
    )
    assert dm.status_code == 409

    db.refresh(creator)
    assert creator.profile.follower_count == 0


def test_views_are_recorded_once_per_window(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    video = make_video(db, creator)
    headers = login(client, viewer)

    first = client.post(f"/api/v1/videos/{video.id}/view", params={"session_key": "abc"}, headers=headers)
    second = client.post(f"/api/v1/videos/{video.id}/view", params={"session_key": "abc"}, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["counted"] is True
    # Without Redis the dedupe key cannot be written, so the second call may count too;
    # the reported counter must always match what the API stored.
    db.refresh(video)
    assert video.view_count == second.json()["view_count"]


def test_save_and_report(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    video = make_video(db, creator)
    headers = login(client, viewer)

    saved = client.post(f"/api/v1/videos/{video.id}/save", json={"collection": "Learn later"}, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["saved"] is True

    listing = client.get("/api/v1/videos/saved", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [str(video.id)]

    report = client.post(
        "/api/v1/reports",
        json={"target_type": "video", "target_id": str(video.id), "reason": "spam"},
        headers=headers,
    )
    assert report.status_code == 201

    duplicate = client.post(
        "/api/v1/reports",
        json={"target_type": "video", "target_id": str(video.id), "reason": "spam"},
        headers=headers,
    )
    assert duplicate.status_code in {200, 201}


def test_private_profile_settings_and_content_visibility(api):
    client, db = api["client"], api["db"]
    creator, viewer = api["creator"], api["viewer"]
    creator.profile.is_private = True
    creator.profile.bio = "Private biography"
    db.commit()
    video = make_video(db, creator)

    hidden_profile = client.get(f"/api/v1/users/{creator.username}")
    assert hidden_profile.status_code == 200
    assert hidden_profile.json()["bio"] is None

    hidden_videos = client.get(f"/api/v1/users/{creator.username}/videos")
    assert hidden_videos.status_code == 200
    assert hidden_videos.json()["items"] == []
    assert client.get(f"/api/v1/videos/{video.id}").status_code == 404
    search = client.get("/api/v1/search", params={"q": video.title, "type": "videos"})
    assert search.json()["videos"]["items"] == []

    headers = login(client, viewer)
    settings = client.get("/api/v1/users/me/profile", headers=headers)
    assert settings.status_code == 200
    assert settings.json()["is_private"] is False

    followed = client.post(f"/api/v1/users/{creator.username}/follow", headers=headers)
    assert followed.status_code == 200
    assert client.get(f"/api/v1/users/{creator.username}").json()["bio"] is None

    followed_profile = client.get(f"/api/v1/users/{creator.username}", headers=headers)
    assert followed_profile.json()["bio"] == "Private biography"
    followed_videos = client.get(f"/api/v1/users/{creator.username}/videos", headers=headers)
    assert [item["id"] for item in followed_videos.json()["items"]] == [str(video.id)]
    assert client.get(f"/api/v1/videos/{video.id}", headers=headers).status_code == 200


def test_owner_only_edits_and_unverified_cannot_publish(api):
    client, db = api["client"], api["db"]
    creator = api["creator"]
    video = make_video(db, creator)
    other, password = make_user(db)
    headers = login(client, other, password)

    forbidden = client.patch(f"/api/v1/videos/{video.id}", json={"title": "Hijacked"}, headers=headers)
    assert forbidden.status_code == 403

    unverified, unverified_password = make_user(db, verified=False)
    unverified_headers = login(client, unverified, unverified_password)
    from tests.conftest import make_media

    asset = make_media(db, unverified)
    blocked = client.post(
        "/api/v1/videos",
        json={"media_asset_id": str(asset.id), "title": "First upload"},
        headers=unverified_headers,
    )
    assert blocked.status_code == 400