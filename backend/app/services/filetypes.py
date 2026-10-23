"""Content sniffing — never trust the MIME type a client declares."""

from __future__ import annotations

from pathlib import Path

VIDEO_SIGNATURES: tuple[tuple[bytes, int, str], ...] = (
    (b"\x00\x00\x00\x18ftyp", 0, "video/mp4"),
    (b"\x00\x00\x00\x20ftyp", 0, "video/mp4"),
    (b"\x1a\x45\xdf\xa3", 0, "video/webm"),
    (b"FLV", 0, "video/x-flv"),
    (b"RIFF", 0, "video/avi"),
)
ISO_MEDIA_BRANDS: dict[bytes, str] = {
    b"isom": "video/mp4",
    b"iso2": "video/mp4",
    b"mp41": "video/mp4",
    b"mp42": "video/mp4",
    b"avc1": "video/mp4",
    b"M4V ": "video/x-m4v",
    b"qt  ": "video/quicktime",
    b"msdh": "video/mp4",
}

IMAGE_SIGNATURES: tuple[tuple[bytes, int, str], ...] = (
    (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png"),
    (b"GIF87a", 0, "image/gif"),
    (b"GIF89a", 0, "image/gif"),
)

AUDIO_SIGNATURES: tuple[tuple[bytes, int, str], ...] = (
    (b"ID3", 0, "audio/mpeg"),
    (b"OggS", 0, "audio/ogg"),
    (b"fLaC", 0, "audio/flac"),
)


def _match(prefix: bytes, signatures: tuple[tuple[bytes, int, str], ...]) -> str | None:
    for signature, offset, content_type in signatures:
        if prefix[offset : offset + len(signature)] == signature:
            return content_type
    return None


def detect_content_type(prefix: bytes) -> str | None:
    """Identify the real type from the first bytes of the file."""
    if not prefix:
        return None
    if prefix[4:8] == b"ftyp":
        return ISO_MEDIA_BRANDS.get(prefix[8:12], "video/mp4")
    for group in (VIDEO_SIGNATURES, IMAGE_SIGNATURES, AUDIO_SIGNATURES):
        detected = _match(prefix, group)
        if detected:
            return detected
    if prefix[0:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    if prefix[:4] == b"\x00\x00\x00\x14" or prefix[:4] == b"\x00\x00\x00\x1c":
        return "video/mp4"
    if prefix[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if prefix[:4] in (b"M4A ",) or prefix[4:8] == b"M4A ":
        return "audio/mp4"
    return None


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_allowed_extension(kind: str, filename: str) -> bool:
    extension = extension_of(filename)
    allowed = {
        "video": {".mp4", ".mov", ".m4v", ".webm", ".mkv"},
        "image": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
        "audio": {".mp3", ".m4a", ".wav", ".ogg", ".flac"},
    }
    return extension in allowed.get(kind, set())


def is_type_valid_for_kind(kind: str, detected: str | None, declared: str | None) -> bool:
    """A video upload must really be video bytes; a declared PNG full of video bytes is rejected."""
    if detected is None:
        # Some containers (e.g. fragmented MP4 variants) hide their signature; fall back to
        # the declared type only when it is consistent with the requested kind.
        if not declared:
            return False
        return declared.startswith(f"{kind}/")
    if kind == "image":
        return detected.startswith("image/")
    if kind == "video":
        return detected.startswith("video/")
    return detected.startswith("audio/")