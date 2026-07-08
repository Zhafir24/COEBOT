"""Local user store with scrypt password hashing + active-session tracker.

Users are persisted to a JSON file (default: ``data/users.json``).
Passwords are never stored in plaintext — each user has a 16-byte random
salt and a 64-byte scrypt-derived key, both base64-encoded in the JSON.

Active sessions are tracked in a separate JSON file so that a browser
refresh restores the signed-in user.

The store is fully local — no network calls, no external services. The
files' parent directories are created on first write.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SALT_BYTES = 16

_MIN_USERNAME_LEN = 3
_MAX_USERNAME_LEN = 32
_MIN_PASSWORD_LEN = 6


@dataclass(frozen=True, slots=True)
class User:
    """A registered local user."""

    username: str
    password_hash: bytes
    salt: bytes
    created_at: str


class UserStoreError(Exception):
    """Base class for user-store failures surfaced to the UI."""


class UserStore:
    """JSON-backed user store with scrypt password hashing."""

    def __init__(self, store_path: Path) -> None:
        self._path = store_path

    # ---------- Public API ------------------------------------------------

    def has_users(self) -> bool:
        """True if at least one user is registered."""
        return bool(self._load().get("users"))

    def get(self, username: str) -> User | None:
        """Look up a user by username. Returns None if not found."""
        users = self._load().get("users", {})
        raw = users.get(username)
        if not raw:
            return None
        return User(
            username=raw["username"],
            password_hash=base64.b64decode(raw["password_hash"]),
            salt=base64.b64decode(raw["salt"]),
            created_at=raw["created_at"],
        )

    def register(self, username: str, password: str) -> User:
        """Create a new user.

        Raises:
            UserStoreError: if validation fails or the username is taken.
        """
        username = (username or "").strip()
        password = password or ""

        if len(username) < _MIN_USERNAME_LEN:
            raise UserStoreError(
                f"Username must be at least {_MIN_USERNAME_LEN} characters."
            )
        if len(username) > _MAX_USERNAME_LEN:
            raise UserStoreError(
                f"Username must be at most {_MAX_USERNAME_LEN} characters."
            )
        if not username.replace("_", "").replace("-", "").isalnum():
            raise UserStoreError(
                "Username may only contain letters, digits, underscores, or hyphens."
            )
        if len(password) < _MIN_PASSWORD_LEN:
            raise UserStoreError(
                f"Password must be at least {_MIN_PASSWORD_LEN} characters."
            )
        if self.get(username) is not None:
            raise UserStoreError(f"Username '{username}' is already taken.")

        salt = os.urandom(_SALT_BYTES)
        password_hash = self._hash(password, salt)
        user = User(
            username=username,
            password_hash=password_hash,
            salt=salt,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

        data = self._load()
        users = data.setdefault("users", {})
        users[username] = {
            "username": user.username,
            "password_hash": base64.b64encode(user.password_hash).decode("ascii"),
            "salt": base64.b64encode(user.salt).decode("ascii"),
            "created_at": user.created_at,
        }
        self._save(data)
        return user

    def authenticate(self, username: str, password: str) -> bool:
        """Constant-time credential check. Returns True if valid."""
        user = self.get(username)
        if user is None:
            # Hash a dummy attempt anyway to even out timing.
            self._hash(password or "", b"\x00" * _SALT_BYTES)
            return False
        candidate = self._hash(password or "", user.salt)
        return hmac.compare_digest(user.password_hash, candidate)

    # ---------- Internals -------------------------------------------------

    @staticmethod
    def _hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN,
        )

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically: write to a temp file, then rename.
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._path)


# ----------------------------------------------------------------------------
# Active session tracker
# ----------------------------------------------------------------------------


_SESSION_TTL = timedelta(days=7)


class ActiveSessionStore:
    """Single-active-session tracker for the local device.

    Persists "who's currently signed in" to a JSON file so that
    refreshing the browser doesn't kick the user back to login. Treated
    as a single-user-per-device assumption — appropriate for the local,
    fully-local deployment model.
    """

    def __init__(self, path: Path, ttl: timedelta = _SESSION_TTL) -> None:
        self._path = path
        self._ttl = ttl

    def get_active_user(self) -> str | None:
        """Return the currently active username, or None if no live session."""
        data = self._load()
        if not data:
            return None
        try:
            expires = datetime.fromisoformat(data["expires_at"])
        except (KeyError, ValueError):
            return None
        if expires < datetime.now(UTC):
            self.clear()
            return None
        return data.get("username")

    def set_active_user(self, username: str) -> None:
        expires_at = (datetime.now(UTC) + self._ttl).isoformat()
        self._save({"username": username, "expires_at": expires_at})

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()

    def _load(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._path)
