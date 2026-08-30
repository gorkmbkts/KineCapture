"""SQLite connection policy and idempotent identity schema installation."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

IDENTITY_SCHEMA_VERSION = 1


class IdentityDatabase:
    """Short-lived SQLite connections with explicit transaction boundaries."""

    def __init__(self, path: Path, *, busy_timeout_ms: int = 5000) -> None:
        self.path = Path(path).expanduser().resolve()
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1000.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        # DELETE journal mode is intentional: operations are tiny and local,
        # and avoiding persistent WAL sidecars makes backup/relocation safer.
        connection.execute("PRAGMA journal_mode = DELETE")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def initialize(self) -> None:
        with self.transaction(immediate=True) as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > IDENTITY_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Kimlik veritabanı şeması desteklenmiyor: {current}"
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_normalized TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    password_algorithm TEXT NOT NULL,
                    password_parameters TEXT NOT NULL,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL CHECK (role IN ('owner', 'user')),
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                    must_change_password INTEGER NOT NULL DEFAULT 0
                        CHECK (must_change_password IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_owner
                    ON users(role) WHERE role = 'owner';

                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL,
                    project_path_normalized TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS project_access (
                    user_id TEXT NOT NULL REFERENCES users(user_id),
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    assigned_by_user_id TEXT NOT NULL REFERENCES users(user_id),
                    assigned_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, project_id)
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    actor_user_id TEXT REFERENCES users(user_id),
                    target_user_id TEXT REFERENCES users(user_id),
                    project_id TEXT REFERENCES projects(project_id),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT INTO app_metadata(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("schema_version", str(IDENTITY_SCHEMA_VERSION)),
            )
            connection.execute(f"PRAGMA user_version = {IDENTITY_SCHEMA_VERSION}")


__all__ = ["IDENTITY_SCHEMA_VERSION", "IdentityDatabase"]
