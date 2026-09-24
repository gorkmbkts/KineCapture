"""Release gate B3: the installer's System Owner - a digest in, never a password.

Every seed here is made from a test-only password generated for this file. No
real account's password appears in the repository, and none is needed: the
properties under test are the same for any password.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from kinecapture.core.config import AppConfig, default_identity_database_path
from kinecapture.identity.database import IdentityDatabase
from kinecapture.identity.models import UserRole
from kinecapture.identity.passwords import hash_password
from kinecapture.identity.seed import (
    OwnerSeed,
    SeedOutcome,
    apply_owner_seed,
    load_owner_seed,
    seed_document,
)
from kinecapture.identity.service import AuthenticationError, IdentityService
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.viewmodels.auth import AuthMode, AuthViewModel

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts" / "release"))

#: Test-only. It exists nowhere but in this file and the temporary seeds below.
TEST_PASSWORD = "yalniz-test-icin-7Q"
PROFILE = {
    "username": "gorkembektas",
    "first_name": "Görkem",
    "last_name": "Bektaş",
    "title": "Test unvanı",
}


def _document(password: str = TEST_PASSWORD) -> dict:
    seed = OwnerSeed(**PROFILE, digest=hash_password(password))
    return seed_document(seed, created_at="2026-09-23T00:00:00Z", generator="test")


def _write(path: Path, document) -> Path:  # noqa: ANN001
    path.parent.mkdir(parents=True, exist_ok=True)
    text = document if isinstance(document, str) else json.dumps(document, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def seed_file(tmp_path) -> Path:
    return _write(tmp_path / "install" / "share" / "kinecapture" / "owner_seed.json", _document())


def _identity(root: Path) -> IdentityService:
    return IdentityService(IdentityDatabase(root / "identity.sqlite3"))


def _users(identity: IdentityService) -> list[tuple]:
    with identity.database.connection() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                "SELECT user_id, username, role, password_hash, password_salt FROM users ORDER BY user_id"
            )
        ]


def _audit(identity: IdentityService) -> list[tuple]:
    with identity.database.connection() as connection:
        return [
            (row[0], json.loads(row[1]))
            for row in connection.execute(
                "SELECT event_type, metadata_json FROM audit_log ORDER BY audit_id"
            )
        ]


# ------------------------------------------------------------ first start
def test_a_seed_creates_the_owner_on_an_empty_database(tmp_path, seed_file) -> None:
    identity = _identity(tmp_path / "state")
    result = apply_owner_seed(identity, seed_file)
    assert result.outcome is SeedOutcome.CREATED
    assert not identity.needs_initial_setup
    user = identity.repository.get_user_by_normalized_username("gorkembektas")
    assert user is not None and user.role is UserRole.OWNER
    assert (user.first_name, user.last_name, user.title) == ("Görkem", "Bektaş", "Test unvanı")
    stored = _users(identity)[0]
    seed = load_owner_seed(seed_file)
    assert (stored[3], stored[4]) == (seed.digest.hash_b64, seed.digest.salt_b64)
    assert _audit(identity) == [("user_created", {"role": "owner", "origin": "owner_seed"})]


def test_with_a_seed_the_setup_form_never_appears(tmp_path, seed_file) -> None:
    session = SessionService.open(AppConfig.sandboxed(tmp_path / "state"), owner_seed=seed_file)
    auth = AuthViewModel(session)
    assert auth.mode is AuthMode.SIGN_IN
    assert auth.startup_notice is not None and auth.startup_notice.severity.value == "info"
    assert auth.remembered_username == "gorkembektas"


def test_without_a_seed_the_first_run_is_unchanged(tmp_path) -> None:
    session = SessionService.open(
        AppConfig.sandboxed(tmp_path / "state"), owner_seed=tmp_path / "missing.json"
    )
    auth = AuthViewModel(session)
    assert session.needs_initial_setup
    assert auth.mode is AuthMode.SETUP
    assert session.startup_notice is None and auth.startup_notice is None


def test_the_right_password_signs_in_and_a_wrong_one_does_not(tmp_path, seed_file) -> None:
    session = SessionService.open(AppConfig.sandboxed(tmp_path / "state"), owner_seed=seed_file)
    with pytest.raises(AuthenticationError):
        session.sign_in("gorkembektas", TEST_PASSWORD + "x")
    user = session.sign_in("gorkembektas", TEST_PASSWORD)
    assert user.is_owner
    assert session.is_authenticated


def test_the_ordinary_owner_form_still_works(tmp_path) -> None:
    identity = _identity(tmp_path / "state")
    identity.create_initial_owner(password=TEST_PASSWORD, **PROFILE)
    assert _audit(identity) == [("user_created", {"role": "owner"})]
    assert identity.authenticate("gorkembektas", TEST_PASSWORD).is_owner


# ------------------------------------------------- a database already here
def test_a_database_with_accounts_is_left_exactly_as_it_was(tmp_path, seed_file) -> None:
    identity = _identity(tmp_path / "state")
    identity.create_initial_owner(
        password="baska-bir-test-parolasi", username="onceki.sahip",
        first_name="Önceki", last_name="Sahip", title="",
    )
    before_users, before_audit = _users(identity), _audit(identity)
    result = apply_owner_seed(identity, seed_file)
    assert result.outcome is SeedOutcome.SKIPPED_EXISTING
    assert result.is_warning and "dokunulmadı" in result.detail
    assert _users(identity) == before_users
    assert _audit(identity) == before_audit


def test_a_filled_database_is_explained_at_the_sign_in_form(tmp_path, seed_file) -> None:
    config = AppConfig.sandboxed(tmp_path / "state")
    _identity(tmp_path / "state").create_initial_owner(
        password="baska-bir-test-parolasi", username="onceki.sahip",
        first_name="Önceki", last_name="Sahip", title="",
    )
    auth = AuthViewModel(SessionService.open(config, owner_seed=seed_file))
    assert auth.mode is AuthMode.SIGN_IN
    assert auth.startup_notice is not None
    assert auth.startup_notice.severity.value == "warning"


def test_starting_again_after_the_seed_is_quiet(tmp_path, seed_file) -> None:
    config = AppConfig.sandboxed(tmp_path / "state")
    SessionService.open(config, owner_seed=seed_file)
    again = SessionService.open(config, owner_seed=seed_file)
    assert again.startup_notice is None
    assert apply_owner_seed(again.identity, seed_file).outcome is SeedOutcome.ALREADY_PRESENT
    assert len(_users(again.identity)) == 1


# --------------------------------------------------------- a broken seed
def _broken(case: str) -> object:
    document = _document()
    if case == "not_json":
        return "{ bu json değil"
    if case == "no_title":
        document["title"] = "  "
    elif case == "algorithm":
        document["password"]["algorithm"] = "md5"
    elif case == "hash_not_base64":
        document["password"]["hash"] = "***"
    elif case == "hash_length":
        document["password"]["hash"] = document["password"]["salt"]
    elif case == "plaintext_rides_along":
        document["plaintext"] = "bir parola"
    elif case == "password_as_text":
        document["password"] = "bir parola"
    elif case == "role":
        document["role"] = "user"
    elif case == "n_not_power_of_two":
        document["password"]["parameters"]["n"] = 1000
    elif case == "memory":
        document["password"]["parameters"]["n"] = 2**20
    elif case == "username":
        document["username"] = "a"
    elif case == "schema":
        document["schema_version"] = 99
    return document


@pytest.mark.parametrize(
    "case",
    [
        "not_json", "no_title", "algorithm", "hash_not_base64", "hash_length",
        "plaintext_rides_along", "password_as_text", "role", "n_not_power_of_two",
        "memory", "username", "schema",
    ],
)
def test_a_broken_seed_creates_nothing_and_says_so(tmp_path, case) -> None:
    seed = _write(tmp_path / "owner_seed.json", _broken(case))
    identity = _identity(tmp_path / "state")
    result = apply_owner_seed(identity, seed)
    assert result.outcome is SeedOutcome.INVALID
    assert identity.needs_initial_setup
    assert _users(identity) == []
    auth = AuthViewModel(
        SessionService.open(AppConfig.sandboxed(tmp_path / "state"), owner_seed=seed)
    )
    assert auth.mode is AuthMode.SETUP
    assert auth.startup_notice is not None and auth.startup_notice.severity.value == "warning"


# ------------------------------------------- another Windows user, same PC
def test_every_windows_user_gets_the_owner_from_the_same_seed(tmp_path, seed_file, monkeypatch) -> None:
    """The identity database is per user (``%LOCALAPPDATA%``); the seed is per
    installation. Two users, two empty databases, the same owner in both."""
    for name in ("KullaniciA", "Kullanıcı B"):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / name / "AppData" / "Local"))
        path = default_identity_database_path()
        assert str(tmp_path / name) in str(path)
        session = SessionService.open(_config(tmp_path / name, path), owner_seed=seed_file)
        assert session.startup_notice is not None
        assert session.sign_in("gorkembektas", TEST_PASSWORD).is_owner
    assert (tmp_path / "KullaniciA" / "AppData" / "Local" / "KineCapture" / "identity.sqlite3").is_file()
    assert (tmp_path / "Kullanıcı B" / "AppData" / "Local" / "KineCapture" / "identity.sqlite3").is_file()


def _config(root: Path, identity_path: Path) -> AppConfig:
    config = AppConfig.sandboxed(root)
    config.identity_db_path = identity_path
    return config


# ---------------------------------------------------------- the generator
def test_the_generator_writes_the_digest_and_nothing_else(tmp_path) -> None:
    import make_owner_seed

    answers = iter([TEST_PASSWORD, TEST_PASSWORD])
    out = tmp_path / "dist" / "owner_seed.json"
    seed = make_owner_seed.make_seed(out, **PROFILE, prompt=lambda _: next(answers))
    text = out.read_text("utf-8")
    assert TEST_PASSWORD not in text
    document = json.loads(text)
    assert set(document["password"]) == {"algorithm", "parameters", "salt", "hash"}
    assert document["password"]["algorithm"] == "scrypt-v1"
    assert seed.username == "gorkembektas"
    identity = _identity(tmp_path / "state")
    assert apply_owner_seed(identity, out).outcome is SeedOutcome.CREATED
    assert identity.authenticate("gorkembektas", TEST_PASSWORD).is_owner


@pytest.mark.parametrize(
    "answers, reason",
    [
        ([TEST_PASSWORD, TEST_PASSWORD + "!"], "eşleşmedi"),
        (["kisa", "kisa"], "Parola kabul edilmedi"),
    ],
)
def test_the_generator_writes_nothing_on_a_bad_entry(tmp_path, answers, reason) -> None:
    import make_owner_seed

    replies = iter(answers)
    out = tmp_path / "dist" / "owner_seed.json"
    with pytest.raises(SystemExit) as stopped:
        make_owner_seed.make_seed(out, **PROFILE, prompt=lambda _: next(replies))
    assert reason in str(stopped.value)
    assert not out.exists()


def test_the_generator_requires_a_title(tmp_path) -> None:
    import make_owner_seed

    with pytest.raises(SystemExit):
        make_owner_seed.make_seed(
            tmp_path / "dist" / "owner_seed.json",
            **{**PROFILE, "title": " "},
            prompt=lambda _: TEST_PASSWORD,
        )


def test_the_generator_writes_only_into_build_output() -> None:
    import make_owner_seed

    with pytest.raises(SystemExit):
        make_owner_seed._output_path("owner_seed.json")
    with pytest.raises(SystemExit):
        make_owner_seed._output_path("src/owner_seed.json")
    assert make_owner_seed._output_path("dist/owner_seed.json").name == "owner_seed.json"
    assert make_owner_seed._output_path("build/x/owner_seed.json").parent.name == "x"


def test_no_seed_is_tracked_by_git() -> None:
    import subprocess

    repo = HERE.parent
    tracked = subprocess.run(
        ["git", "ls-files", "--", "*owner_seed*.json"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert tracked == []
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "dist/owner_seed.json"], cwd=repo
    )
    assert ignored.returncode == 0
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "owner_seed.json"], cwd=repo
    )
    assert ignored.returncode == 0


def test_the_database_file_is_real_sqlite(tmp_path, seed_file) -> None:
    """Guard for the fixtures: a seed never lands anywhere but the database."""
    identity = _identity(tmp_path / "state")
    apply_owner_seed(identity, seed_file)
    with sqlite3.connect(tmp_path / "state" / "identity.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
