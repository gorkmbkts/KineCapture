"""Authentication, authorization and project-registration policy."""

from __future__ import annotations

import json

import os
import re
import shutil
import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional

from kinecapture.core.errors import KineCaptureError, StorageError, ValidationError
from kinecapture.core.ids import new_id, utc_now_iso
from kinecapture.core.jsonio import read_json_mapping
from kinecapture.core.logging import get_logger
from kinecapture.dataset.workspace import PROJECT_FILE, ProjectWorkspace
from kinecapture.domain.project import CaptureProfile
from kinecapture.identity.database import IdentityDatabase
from kinecapture.identity.models import ProjectAccess, User, UserRole, UserSummary
from kinecapture.identity.passwords import hash_password, validate_password, verify_password
from kinecapture.identity.repository import IdentityRepository

_USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


class AuthenticationError(KineCaptureError):
    code = "authentication_failed"


logger = get_logger(__name__)


class AuthorizationError(KineCaptureError):
    code = "authorization_denied"


def normalize_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username.strip()).casefold()


def normalize_project_path(path: Path) -> str:
    resolved = Path(path).expanduser().resolve()
    return os.path.normcase(str(resolved)).casefold()


def _validate_profile(
    *, first_name: str, last_name: str, title: str, username: str
) -> tuple[str, str, str, str, str]:
    first = first_name.strip()
    last = last_name.strip()
    job_title = title.strip()
    shown_username = username.strip()
    if not first:
        raise ValidationError("Ad zorunludur.", field="first_name", code="first_name_empty")
    if not last:
        raise ValidationError("Soyad zorunludur.", field="last_name", code="last_name_empty")
    if not _USERNAME.fullmatch(shown_username):
        raise ValidationError(
            "Kullanıcı adı 3-64 karakter olmalı; yalnızca harf, rakam, nokta, "
            "alt çizgi ve kısa çizgi içerebilir.",
            field="username",
            code="username_invalid",
        )
    if any(len(value) > 128 for value in (first, last, job_title)):
        raise ValidationError("Ad alanlarından biri çok uzun.", code="profile_too_long")
    return first, last, job_title, shown_username, normalize_username(shown_username)


class IdentityService:
    """The only application-level authority for identity and project access."""

    def __init__(self, database: IdentityDatabase) -> None:
        self.database = database
        self.repository = IdentityRepository(database)

    @property
    def needs_initial_setup(self) -> bool:
        return self.repository.user_count() == 0

    def _insert_user(
        self,
        *,
        first_name: str,
        last_name: str,
        title: str,
        username: str,
        password: str,
        role: UserRole,
        must_change_password: bool = False,
        actor_user_id: Optional[str] = None,
        require_empty: bool = False,
    ) -> User:
        first, last, job, shown, normalized = _validate_profile(
            first_name=first_name,
            last_name=last_name,
            title=title,
            username=username,
        )
        digest = hash_password(password)
        user_id = new_id("usr")
        now = utc_now_iso()
        try:
            with self.database.transaction(immediate=True) as connection:
                if require_empty and int(
                    connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                ):
                    raise ValidationError(
                        "İlk kurulum daha önce tamamlanmış.", code="setup_already_complete"
                    )
                self.repository.insert_user(
                    connection,
                    user_id=user_id,
                    username=shown,
                    normalized=normalized,
                    digest=digest,
                    first_name=first,
                    last_name=last,
                    title=job,
                    role=role,
                    now=now,
                    must_change_password=must_change_password,
                )
                self.repository.audit(
                    connection,
                    "user_created",
                    now,
                    actor_user_id=actor_user_id or user_id,
                    target_user_id=user_id,
                    metadata={"role": role.value},
                )
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "username" in message:
                raise ValidationError(
                    "Bu kullanıcı adı zaten kullanılıyor.",
                    field="username",
                    code="username_duplicate",
                ) from exc
            if role is UserRole.OWNER:
                raise ValidationError(
                    "Sistemde yalnızca bir Sistem Sahibi olabilir.",
                    code="owner_already_exists",
                ) from exc
            raise
        user = self.repository.get_user(user_id)
        assert user is not None
        return user

    def create_initial_owner(self, **fields: str) -> User:
        return self._insert_user(
            **fields, role=UserRole.OWNER, require_empty=True
        )

    def self_register(self, **fields: str) -> User:
        if self.needs_initial_setup:
            raise ValidationError(
                "Önce Sistem Sahibi hesabı oluşturulmalıdır.", code="setup_required"
            )
        return self._insert_user(**fields, role=UserRole.USER)

    def create_user(self, actor: User, **fields: str) -> User:
        current = self.require_owner(actor)
        return self._insert_user(
            **fields, role=UserRole.USER, actor_user_id=current.user_id
        )

    def authenticate(self, username: str, password: str) -> User:
        normalized = normalize_username(username)
        row = self.repository.password_row(normalized)
        generic = AuthenticationError(
            "Kullanıcı adı veya parola hatalı.",
            remedy="Bilgilerinizi ve Caps Lock durumunu kontrol edin.",
        )
        if row is None or not verify_password(
            password,
            algorithm=str(row["password_algorithm"]),
            parameters_json=str(row["password_parameters"]),
            salt_b64=str(row["password_salt"]),
            hash_b64=str(row["password_hash"]),
        ):
            raise generic
        if not bool(row["is_active"]):
            raise AuthenticationError(
                "Bu hesap pasif durumda; oturum açılamadı.",
                remedy="Sistem Sahibinizle iletişime geçin.",
                code="account_inactive",
            )
        now = utc_now_iso()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE user_id = ?",
                (now, now, str(row["user_id"])),
            )
            self.repository.audit(
                connection, "login_succeeded", now, actor_user_id=str(row["user_id"])
            )
        user = self.repository.get_user(str(row["user_id"]))
        assert user is not None
        return user

    def require_active(self, user: User) -> User:
        current = self.repository.get_user(user.user_id)
        if current is None or not current.is_active:
            raise AuthorizationError(
                "Hesabınız artık aktif değil.",
                remedy="Yeniden giriş yapın veya Sistem Sahibinizle görüşün.",
                code="active_user_required",
            )
        return current

    def require_owner(self, user: User) -> User:
        current = self.require_active(user)
        if not current.is_owner:
            raise AuthorizationError(
                "Bu işlem yalnızca Sistem Sahibi tarafından yapılabilir.",
                code="owner_required",
            )
        return current

    def change_password(
        self, user: User, *, current_password: str, new_password: str
    ) -> User:
        current = self.require_active(user)
        row = self.repository.password_row(normalize_username(current.username))
        if row is None or not verify_password(
            current_password,
            algorithm=str(row["password_algorithm"]),
            parameters_json=str(row["password_parameters"]),
            salt_b64=str(row["password_salt"]),
            hash_b64=str(row["password_hash"]),
        ):
            raise AuthenticationError(
                "Mevcut şifre doğru değil.", code="current_password_invalid"
            )
        digest = hash_password(new_password)
        now = utc_now_iso()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE users SET password_hash=?, password_salt=?,
                    password_algorithm=?, password_parameters=?,
                    must_change_password=0, updated_at=? WHERE user_id=?
                """,
                (
                    digest.hash_b64,
                    digest.salt_b64,
                    digest.algorithm,
                    digest.parameters_json,
                    now,
                    current.user_id,
                ),
            )
            self.repository.audit(
                connection, "password_changed", now, actor_user_id=current.user_id
            )
        refreshed = self.repository.get_user(current.user_id)
        assert refreshed is not None
        return refreshed

    def reset_password(self, actor: User, target_user_id: str, password: str) -> User:
        owner = self.require_owner(actor)
        target = self.repository.get_user(target_user_id)
        if target is None:
            raise ValidationError("Kullanıcı bulunamadı.", code="user_not_found")
        digest = hash_password(password)
        now = utc_now_iso()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE users SET password_hash=?, password_salt=?,
                    password_algorithm=?, password_parameters=?,
                    must_change_password=1, updated_at=? WHERE user_id=?
                """,
                (
                    digest.hash_b64,
                    digest.salt_b64,
                    digest.algorithm,
                    digest.parameters_json,
                    now,
                    target.user_id,
                ),
            )
            self.repository.audit(
                connection,
                "password_reset",
                now,
                actor_user_id=owner.user_id,
                target_user_id=target.user_id,
            )
        refreshed = self.repository.get_user(target.user_id)
        assert refreshed is not None
        return refreshed

    def update_user(
        self,
        actor: User,
        target_user_id: str,
        *,
        first_name: str,
        last_name: str,
        title: str,
        username: str,
    ) -> User:
        owner = self.require_owner(actor)
        target = self.repository.get_user(target_user_id)
        if target is None:
            raise ValidationError("Kullanıcı bulunamadı.", code="user_not_found")
        first, last, job, shown, normalized = _validate_profile(
            first_name=first_name,
            last_name=last_name,
            title=title,
            username=username,
        )
        now = utc_now_iso()
        try:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    UPDATE users SET username=?, username_normalized=?, first_name=?,
                        last_name=?, title=?, updated_at=? WHERE user_id=?
                    """,
                    (shown, normalized, first, last, job, now, target.user_id),
                )
                self.repository.audit(
                    connection,
                    "user_updated",
                    now,
                    actor_user_id=owner.user_id,
                    target_user_id=target.user_id,
                )
        except sqlite3.IntegrityError as exc:
            raise ValidationError(
                "Bu kullanıcı adı zaten kullanılıyor.",
                field="username",
                code="username_duplicate",
            ) from exc
        refreshed = self.repository.get_user(target.user_id)
        assert refreshed is not None
        return refreshed

    def set_user_active(self, actor: User, target_user_id: str, active: bool) -> User:
        owner = self.require_owner(actor)
        target = self.repository.get_user(target_user_id)
        if target is None:
            raise ValidationError("Kullanıcı bulunamadı.", code="user_not_found")
        if target.is_owner and not active:
            raise AuthorizationError(
                "Sistem Sahibi pasif yapılamaz.", code="owner_cannot_be_deactivated"
            )
        now = utc_now_iso()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE users SET is_active=?, updated_at=? WHERE user_id=?",
                (int(active), now, target.user_id),
            )
            self.repository.audit(
                connection,
                "user_activation_changed",
                now,
                actor_user_id=owner.user_id,
                target_user_id=target.user_id,
                metadata={"is_active": bool(active)},
            )
        refreshed = self.repository.get_user(target.user_id)
        assert refreshed is not None
        return refreshed

    def delete_user(self, actor: User, target_user_id: str) -> None:
        """Physical deletion is forbidden; historical operator links must survive."""
        self.require_owner(actor)
        target = self.repository.get_user(target_user_id)
        if target is None:
            raise ValidationError("Kullanıcı bulunamadı.", code="user_not_found")
        raise AuthorizationError(
            "Kullanıcılar silinmez; gerektiğinde pasif duruma alınır.",
            code="user_deletion_forbidden",
        )

    def set_user_role(self, actor: User, target_user_id: str, role: UserRole) -> None:
        """Roles are immutable in the single-owner product model."""
        self.require_owner(actor)
        target = self.repository.get_user(target_user_id)
        if target is None:
            raise ValidationError("Kullanıcı bulunamadı.", code="user_not_found")
        raise AuthorizationError(
            "Sistem Sahibi rolü değiştirilemez ve başka kullanıcıya verilemez.",
            code="user_role_immutable",
        )

    def list_users(self, actor: User) -> list[UserSummary]:
        self.require_owner(actor)
        return self.repository.list_users()

    def _validate_project_workspace(self, path: Path) -> tuple[ProjectWorkspace, Path]:
        root = Path(path).expanduser().resolve()
        workspace = ProjectWorkspace.open(root)
        payload = read_json_mapping(root / PROJECT_FILE)
        if str(payload.get("project_id", "")) != workspace.project.project_id:
            raise StorageError("Proje kimliği doğrulanamadı.", code="project_id_mismatch")
        return workspace, root

    def register_project(
        self, actor: User, workspace: ProjectWorkspace, *, owner_user_id: Optional[str] = None
    ) -> ProjectAccess:
        current = self.require_active(actor)
        workspace, root = self._validate_project_workspace(workspace.root)
        project = workspace.project
        target_owner = owner_user_id or current.user_id
        if target_owner != current.user_id:
            self.require_owner(current)
        target = self.repository.get_user(target_owner)
        if target is None or not target.is_active:
            raise ValidationError("Proje sahibi geçerli değil.", code="project_owner_invalid")
        now = utc_now_iso()
        try:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    INSERT INTO projects(project_id, project_path,
                        project_path_normalized, name, description, owner_user_id,
                        created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project.project_id,
                        str(root),
                        normalize_project_path(root),
                        project.name,
                        project.description,
                        target_owner,
                        project.created_at,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO project_access(
                        user_id, project_id, assigned_by_user_id, assigned_at
                    ) VALUES(?, ?, ?, ?)
                    """,
                    (target_owner, project.project_id, current.user_id, now),
                )
                self.repository.audit(
                    connection,
                    "project_registered",
                    now,
                    actor_user_id=current.user_id,
                    project_id=project.project_id,
                )
        except sqlite3.IntegrityError as exc:
            existing = self.repository.get_project(project.project_id)
            if existing is not None and normalize_project_path(existing.path) != normalize_project_path(root):
                raise ValidationError(
                    "Aynı proje kimliği başka bir klasöre kayıtlı.",
                    code="project_id_path_conflict",
                ) from exc
            raise ValidationError(
                "Bu proje klasörü daha önce kaydedilmiş.", code="project_already_registered"
            ) from exc
        record = self.repository.get_project(project.project_id)
        assert record is not None
        return record

    def create_project(
        self,
        actor: User,
        dataset_root: Path,
        name: str,
        *,
        description: str = "",
        capture_profile: Optional[CaptureProfile] = None,
    ) -> ProjectWorkspace:
        current = self.require_active(actor)
        workspace = ProjectWorkspace.create(
            dataset_root,
            name,
            description=description,
            capture_profile=capture_profile,
        )
        try:
            self.register_project(current, workspace)
        except Exception:
            root = workspace.root.resolve()
            projects_root = (Path(dataset_root).expanduser().resolve() / "projects")
            if root.parent == projects_root and (root / PROJECT_FILE).is_file():
                shutil.rmtree(root)
            raise
        return workspace

    def list_projects(self, user: User) -> list[ProjectAccess]:
        return self.repository.list_projects(self.require_active(user))

    def authorize_project(self, user: User, project_id: str) -> ProjectAccess:
        current = self.require_active(user)
        project = self.repository.get_project(project_id)
        if project is None:
            raise AuthorizationError("Proje kayıtlı değil.", code="project_not_registered")
        if current.is_owner or project.owner_user_id == current.user_id:
            return project
        if project.project_id in self.repository.assigned_project_ids(current.user_id):
            return project
        raise AuthorizationError(
            "Bu projeye erişim yetkiniz yok.", code="project_access_denied"
        )

    def authorize_project_path(self, user: User, path: Path) -> ProjectAccess:
        current = self.require_active(user)
        record = self.repository.get_project_by_normalized_path(normalize_project_path(path))
        if record is None:
            raise AuthorizationError(
                "Bu proje klasörü hesabınıza kayıtlı değil.", code="project_path_denied"
            )
        return self.authorize_project(current, record.project_id)

    def assign_project(self, actor: User, user_id: str, project_id: str) -> None:
        owner = self.require_owner(actor)
        target = self.repository.get_user(user_id)
        project = self.repository.get_project(project_id)
        if target is None or project is None:
            raise ValidationError("Kullanıcı veya proje bulunamadı.", code="assignment_target_missing")
        if target.is_owner:
            raise AuthorizationError(
                "Sistem Sahibi zaten bütün projelere erişir.", code="owner_access_is_implicit"
            )
        now = utc_now_iso()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO project_access(user_id, project_id, assigned_by_user_id, assigned_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(user_id, project_id) DO NOTHING
                """,
                (target.user_id, project.project_id, owner.user_id, now),
            )
            self.repository.audit(
                connection, "project_access_assigned", now,
                actor_user_id=owner.user_id, target_user_id=target.user_id,
                project_id=project.project_id,
            )

    def remove_project_access(self, actor: User, user_id: str, project_id: str) -> None:
        owner = self.require_owner(actor)
        target = self.repository.get_user(user_id)
        project = self.repository.get_project(project_id)
        if target is None or project is None:
            raise ValidationError("Kullanıcı veya proje bulunamadı.", code="assignment_target_missing")
        if target.is_owner:
            raise AuthorizationError(
                "Sistem Sahibinin proje erişimi kısıtlanamaz.", code="owner_access_is_implicit"
            )
        if project.owner_user_id == target.user_id:
            raise AuthorizationError(
                "Proje sahibinin erişimi kaldırılamaz.", code="project_owner_access_required"
            )
        now = utc_now_iso()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "DELETE FROM project_access WHERE user_id=? AND project_id=?",
                (target.user_id, project.project_id),
            )
            self.repository.audit(
                connection, "project_access_removed", now,
                actor_user_id=owner.user_id, target_user_id=target.user_id,
                project_id=project.project_id,
            )

    # ------------------------------------------------- permanent deletion
    def authorize_project_deletion(self, actor: User, project_id: str) -> ProjectAccess:
        """The security boundary for destroying a project.

        Deliberately *not* in the Projects page. A normal user who bypasses the
        GUI and calls the service directly must be refused here, which is the
        only place a refusal is worth anything. Being able to open a project,
        or even owning it, is not enough: this is the single system owner's
        decision, because it is the one action that cannot be undone.
        """
        owner = self.require_owner(actor)
        record = self.repository.get_project(project_id)
        if record is None:
            raise ValidationError(
                "Proje kaydı bulunamadı.", code="project_not_registered"
            )
        _ = owner
        return record

    def forget_project(
        self, actor: User, project_id: str, *, path: str = "", orphaned: bool = False
    ) -> None:
        """Remove a project from the database, keeping the audit trail.

        ``audit_log.project_id`` is a foreign key onto ``projects``, so the row
        cannot simply go: SQLite would either refuse or (with a cascade nobody
        asked for) take the history with it. Deleting somebody's security
        history because they deleted a folder is the wrong trade, so the
        references are detached instead and the project's identity is copied
        into each event's metadata first - the history keeps saying what it
        always said, just without a live pointer.
        """
        record = self.authorize_project_deletion(actor, project_id)
        now = utc_now_iso()
        with self.database.transaction(immediate=True) as connection:
            for row in connection.execute(
                "SELECT audit_id, metadata_json FROM audit_log WHERE project_id=?",
                (project_id,),
            ).fetchall():
                try:
                    metadata = json.loads(row["metadata_json"] or "{}")
                except (TypeError, ValueError):  # pragma: no cover - corrupt row
                    metadata = {}
                metadata.setdefault("project_id", project_id)
                metadata.setdefault("project_name", record.name)
                metadata["project_deleted_at"] = now
                connection.execute(
                    "UPDATE audit_log SET project_id=NULL, metadata_json=? "
                    "WHERE audit_id=?",
                    (
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                        row["audit_id"],
                    ),
                )
            connection.execute(
                "DELETE FROM project_access WHERE project_id=?", (project_id,)
            )
            connection.execute(
                "DELETE FROM projects WHERE project_id=?", (project_id,)
            )
            # Two different events on purpose. "The files were destroyed" and
            # "a record pointing at a folder that no longer existed was
            # removed" are not the same thing to whoever reads this later.
            self.repository.audit(
                connection,
                "project_record_removed" if orphaned else "project_deleted",
                now,
                actor_user_id=actor.user_id,
                metadata={
                    "project_id": project_id,
                    "project_name": record.name,
                    "project_path": path or record.path,
                    "reason": (
                        "disk hedefi bulunamadı; yalnız uygulama kaydı kaldırıldı"
                        if orphaned
                        else "proje klasörü kalıcı olarak silindi"
                    ),
                    "files_deleted": not orphaned,
                },
            )
        logger.info("Proje kalıcı olarak silindi: %s (%s)", record.name, project_id)

    def note_deletion_outcome(
        self, actor: User, project_id: str, *, ok: bool, detail: str = ""
    ) -> None:
        """Record how the physical removal actually went.

        Separate from :meth:`forget_project` because the filesystem finishes
        after the database does, and a half-removed tree is exactly the thing
        an audit trail should not be silent about.
        """
        with self.database.transaction(immediate=True) as connection:
            self.repository.audit(
                connection,
                "project_files_removed" if ok else "project_files_remaining",
                utc_now_iso(),
                actor_user_id=actor.user_id,
                metadata={"project_id": project_id, "detail": detail},
            )

    def assigned_project_ids(self, actor: User, user_id: str) -> set[str]:
        self.require_owner(actor)
        target = self.repository.get_user(user_id)
        if target is None:
            raise ValidationError("Kullanıcı bulunamadı.", code="user_not_found")
        if target.is_owner:
            return {p.project_id for p in self.repository.list_projects(target)}
        owned = {
            p.project_id for p in self.repository.list_projects(target)
            if p.owner_user_id == target.user_id
        }
        return owned | self.repository.assigned_project_ids(target.user_id)


__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "IdentityService",
    "normalize_project_path",
    "normalize_username",
]
