from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from kms.catalog import Catalog, _now

PBKDF_ROUNDS = 120_000
SESSION_DAYS = 7


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('ascii'),
        PBKDF_ROUNDS,
    )
    return f'{salt}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _digest = stored.split('$', 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""


class Accounts:
    def __init__(self, catalog: Catalog) -> None:
        self.conn = catalog.conn
        self.conn.executescript(USER_SCHEMA)
        self.conn.commit()
        self._bootstrap_admin()

    def _bootstrap_admin(self) -> None:
        count = self.conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if count:
            return
        password = os.environ.get('KMS_ADMIN_PASSWORD', 'admin123').strip() or 'admin123'
        self.create_user('admin', password, role='admin')

    def create_user(self, username: str, password: str, role: str = 'user') -> int:
        username = (username or '').strip()
        if not username or len(username) < 2:
            raise ValueError('username too short')
        if len(password or '') < 6:
            raise ValueError('password must be at least 6 characters')
        if role not in {'admin', 'user'}:
            raise ValueError('role must be admin or user')
        exists = self.conn.execute(
            'SELECT id FROM users WHERE username = ?',
            (username,),
        ).fetchone()
        if exists:
            raise ValueError('username already exists')
        cursor = self.conn.execute(
            """
            INSERT INTO users (username, password_hash, role, active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (username, hash_password(password), role, _now()),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_users(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            'SELECT id, username, role, active, created_at FROM users ORDER BY id'
        ).fetchall()
        return [dict(row) for row in rows]

    def set_active(self, user_id: int, active: bool) -> None:
        self.conn.execute(
            'UPDATE users SET active = ? WHERE id = ?',
            (1 if active else 0, user_id),
        )
        if not active:
            self.conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
        self.conn.commit()

    def set_role(self, user_id: int, role: str) -> None:
        if role not in {'admin', 'user'}:
            raise ValueError('role must be admin or user')
        self.conn.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
        self.conn.commit()

    def set_password(self, user_id: int, password: str) -> None:
        if len(password or '') < 6:
            raise ValueError('password must be at least 6 characters')
        self.conn.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (hash_password(password), user_id),
        )
        self.conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
        self.conn.commit()

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            'SELECT * FROM users WHERE username = ?',
            ((username or '').strip(),),
        ).fetchone()
        if not row:
            return None
        user = dict(row)
        if not user['active'] or not verify_password(password, user['password_hash']):
            return None
        return user

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
        self.conn.execute(
            'INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)',
            (token, user_id, expires.replace(microsecond=0).isoformat()),
        )
        self.conn.commit()
        return token

    def user_from_token(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        row = self.conn.execute(
            """
            SELECT users.id, users.username, users.role, users.active
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, _now()),
        ).fetchone()
        if not row:
            return None
        user = dict(row)
        if not user['active']:
            return None
        return user

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        self.conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
        self.conn.commit()


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'active': bool(user.get('active', 1)),
        'created_at': user.get('created_at') or '',
    }
