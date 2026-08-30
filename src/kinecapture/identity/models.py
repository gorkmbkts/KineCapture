"""Identity-layer value objects. Password material is deliberately absent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class UserRole(str, Enum):
    OWNER = "owner"
    USER = "user"


@dataclass(frozen=True)
class User:
    user_id: str
    username: str
    first_name: str
    last_name: str
    title: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    created_at: str
    updated_at: str
    last_login_at: Optional[str] = None

    @property
    def is_owner(self) -> bool:
        return self.role is UserRole.OWNER

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    @property
    def display_name(self) -> str:
        return self.full_name or self.username


@dataclass(frozen=True)
class ProjectAccess:
    project_id: str
    path: Path
    name: str
    description: str
    owner_user_id: str
    created_at: str


@dataclass(frozen=True)
class UserSummary:
    user: User
    project_count: int


__all__ = ["ProjectAccess", "User", "UserRole", "UserSummary"]
