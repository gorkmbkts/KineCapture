"""Parameterized SQLite queries for identity and project entitlements."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from kinecapture.identity.database import IdentityDatabase
from kinecapture.identity.models import ProjectAccess, User, UserRole, UserSummary
from kinecapture.identity.passwords import PasswordDigest


def _user(row: sqlite3.Row) -> User:
    return User(
        user_id=str(row["user_id"]),
        username=str(row["username"]),
        first_name=str(row["first_name"]),
        last_name=str(row["last_name"]),
        title=str(row["title"]),
        role=UserRole(str(row["role"])),
        is_active=bool(row["is_active"]),
        must_change_password=bool(row["must_change_password"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_login_at=row["last_login_at"],
    )


def _project(row: sqlite3.Row) -> ProjectAccess:
    return ProjectAccess(
        project_id=str(row["project_id"]),
        path=Path(str(row["project_path"])),
        name=str(row["name"]),
        description=str(row["description"]),
        owner_user_id=str(row["owner_user_id"]),
        created_at=str(row["created_at"]),
    )


class IdentityRepository:
    def __init__(self, database: IdentityDatabase) -> None:
        self.database = database

    def user_count(self) -> int:
        with self.database.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def get_user(self, user_id: str) -> Optional[User]:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return _user(row) if row else None

    def get_user_by_normalized_username(self, normalized: str) -> Optional[User]:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username_normalized = ?", (normalized,)
            ).fetchone()
        return _user(row) if row else None

    def password_row(self, normalized: str) -> Optional[sqlite3.Row]:
        with self.database.connection() as connection:
            return connection.execute(
                "SELECT * FROM users WHERE username_normalized = ?", (normalized,)
            ).fetchone()

    @staticmethod
    def insert_user(
        connection: sqlite3.Connection,
        *,
        user_id: str,
        username: str,
        normalized: str,
        digest: PasswordDigest,
        first_name: str,
        last_name: str,
        title: str,
        role: UserRole,
        now: str,
        must_change_password: bool = False,
    ) -> None:
        connection.execute(
            """
            INSERT INTO users(
                user_id, username, username_normalized, password_hash,
                password_salt, password_algorithm, password_parameters,
                first_name, last_name, title, role, is_active,
                must_change_password, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                user_id,
                username,
                normalized,
                digest.hash_b64,
                digest.salt_b64,
                digest.algorithm,
                digest.parameters_json,
                first_name,
                last_name,
                title,
                role.value,
                int(must_change_password),
                now,
                now,
            ),
        )

    def list_users(self) -> list[UserSummary]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT u.*, COUNT(DISTINCT CASE
                    WHEN u.role = 'owner' OR p.owner_user_id = u.user_id OR pa.user_id IS NOT NULL
                    THEN p.project_id END) AS project_count
                FROM users u
                LEFT JOIN projects p ON 1 = 1
                LEFT JOIN project_access pa
                    ON pa.project_id = p.project_id AND pa.user_id = u.user_id
                GROUP BY u.user_id
                ORDER BY CASE u.role WHEN 'owner' THEN 0 ELSE 1 END,
                         u.first_name, u.last_name, u.username
                """
            ).fetchall()
        return [UserSummary(_user(row), int(row["project_count"])) for row in rows]

    def list_projects(self, user: User) -> list[ProjectAccess]:
        with self.database.connection() as connection:
            if user.is_owner:
                rows = connection.execute(
                    "SELECT * FROM projects ORDER BY name COLLATE NOCASE, created_at"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT DISTINCT p.* FROM projects p
                    LEFT JOIN project_access pa ON pa.project_id = p.project_id
                    WHERE p.owner_user_id = ? OR pa.user_id = ?
                    ORDER BY p.name COLLATE NOCASE, p.created_at
                    """,
                    (user.user_id, user.user_id),
                ).fetchall()
        return [_project(row) for row in rows]

    def get_project(self, project_id: str) -> Optional[ProjectAccess]:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        return _project(row) if row else None

    def get_project_by_normalized_path(self, path: str) -> Optional[ProjectAccess]:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE project_path_normalized = ?", (path,)
            ).fetchone()
        return _project(row) if row else None

    def assigned_project_ids(self, user_id: str) -> set[str]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT project_id FROM project_access WHERE user_id = ?", (user_id,)
            ).fetchall()
        return {str(row[0]) for row in rows}

    @staticmethod
    def audit(
        connection: sqlite3.Connection,
        event_type: str,
        now: str,
        *,
        actor_user_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_log(event_type, actor_user_id, target_user_id,
                                  project_id, metadata_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                actor_user_id,
                target_user_id,
                project_id,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )


__all__ = ["IdentityRepository"]
