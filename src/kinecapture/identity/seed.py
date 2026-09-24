"""The installer's ready-made System Owner: a digest, never a password.

A release may carry one file, ``owner_seed.json``, naming the owner and holding
the ``scrypt-v1`` digest of their password. It is made on the owner's own
terminal by ``scripts/release/make_owner_seed.py``; the password itself is
never written anywhere. On a machine whose identity database is still empty,
the first start creates that owner from the digest, so the "create the System
Owner" form never appears. Anywhere else the file changes nothing:

* a database that already has accounts is never touched - not merged, not
  overwritten, not deleted - and the person starting the application is told
  why the packaged account is not there;
* a file that does not read as a seed creates nothing, and the ordinary
  first-run form takes over.

Limit, stated rather than hidden: anyone holding the installer holds the
digest and can try passwords against it offline. Nothing but the digest is in
the file, and scrypt makes each guess expensive; a short or reused password
is still weak.
"""

from __future__ import annotations

import base64
import binascii
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional

from kinecapture.core.errors import KineCaptureError, ValidationError
from kinecapture.core.logging import get_logger
from kinecapture.identity.passwords import ALGORITHM, PasswordDigest
from kinecapture.identity.service import (
    IdentityService,
    _validate_profile,
    normalize_username,
)

logger = get_logger(__name__)

OWNER_SEED_FILE = "owner_seed.json"
OWNER_SEED_SCHEMA = "kinecapture.owner-seed"
OWNER_SEED_SCHEMA_VERSION = 1

_TOP_LEVEL = frozenset(
    {
        "schema",
        "schema_version",
        "username",
        "first_name",
        "last_name",
        "title",
        "role",
        "password",
        "created_at",
        "generator",
    }
)
_DIGEST_KEYS = frozenset({"algorithm", "parameters", "salt", "hash"})
_PARAMETER_KEYS = frozenset({"n", "r", "p", "dklen"})
#: What :func:`kinecapture.identity.passwords.verify_password` can derive. A
#: digest outside it could never be signed in with, so it is refused here.
_MAX_SCRYPT_MEMORY = 64 * 1024 * 1024


class OwnerSeedError(KineCaptureError):
    code = "owner_seed_invalid"


@dataclass(frozen=True)
class OwnerSeed:
    username: str
    first_name: str
    last_name: str
    title: str
    digest: PasswordDigest

    def profile(self) -> dict[str, str]:
        return {
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "title": self.title,
        }


class SeedOutcome(str, Enum):
    ABSENT = "absent"                    # no file: the ordinary first run
    CREATED = "created"                  # owner made from the digest
    ALREADY_PRESENT = "already_present"  # this owner is already here
    SKIPPED_EXISTING = "skipped_existing"  # other accounts: left alone
    INVALID = "invalid"                  # unreadable seed: nothing made


@dataclass(frozen=True)
class SeedResult:
    outcome: SeedOutcome
    username: str = ""
    code: str = ""

    @property
    def headline(self) -> str:
        if self.outcome is SeedOutcome.CREATED:
            return f"Sistem Sahibi hesabı ({self.username}) kurulum paketinden hazırlandı."
        if self.outcome is SeedOutcome.SKIPPED_EXISTING:
            return "Kurulum paketindeki Sistem Sahibi hesabı eklenmedi."
        if self.outcome is SeedOutcome.INVALID:
            return "Kurulum paketindeki Sistem Sahibi bilgisi okunamadı."
        return ""

    @property
    def detail(self) -> str:
        if self.outcome is SeedOutcome.CREATED:
            return "Bu hesabın kullanıcı adı ve parolasıyla giriş yapın."
        if self.outcome is SeedOutcome.SKIPPED_EXISTING:
            return (
                "Bu bilgisayarda daha önce oluşturulmuş hesaplar var; hiçbirine "
                "dokunulmadı. Mevcut bir hesapla giriş yapın."
            )
        if self.outcome is SeedOutcome.INVALID:
            return "Hesap oluşturulmadı. İlk kurulum formuyla devam edebilirsiniz."
        return ""

    @property
    def is_warning(self) -> bool:
        return self.outcome in (SeedOutcome.SKIPPED_EXISTING, SeedOutcome.INVALID)


def default_owner_seed_path() -> Path:
    """Where an installed release keeps its seed: inside its own environment.

    Beside the preview models (``<prefix>/share/kinecapture``), so the file
    belongs to the installation and goes when it is uninstalled.
    """
    return Path(sys.prefix) / "share" / "kinecapture" / OWNER_SEED_FILE


def _fail(reason: str) -> OwnerSeedError:
    return OwnerSeedError(
        "Sistem Sahibi tohum dosyası geçersiz.",
        remedy="Tohumu make_owner_seed.py ile yeniden üretin.",
        details={"reason": reason},
    )


def _decode(value: Any, name: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise _fail(f"{name}_missing")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _fail(f"{name}_not_base64") from exc


def _parameters(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != _PARAMETER_KEYS:
        raise _fail("parameters_shape")
    parameters: dict[str, int] = {}
    for key in sorted(_PARAMETER_KEYS):
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            raise _fail(f"parameter_{key}")
        parameters[key] = item
    n = parameters["n"]
    if n < 2 or n & (n - 1):
        raise _fail("parameter_n_not_power_of_two")
    if 128 * parameters["r"] * n > _MAX_SCRYPT_MEMORY:
        raise _fail("parameters_memory")
    if not 16 <= parameters["dklen"] <= 64:
        raise _fail("parameter_dklen")
    return parameters


def parse_owner_seed(document: Any) -> OwnerSeed:
    """Validate a parsed seed document. Raises :class:`OwnerSeedError`."""
    if not isinstance(document, Mapping):
        raise _fail("not_an_object")
    unknown = set(document) - _TOP_LEVEL
    if unknown:
        # Strict on purpose: the only way a plaintext field could ride along
        # is as a key this reader does not know.
        raise _fail("unknown_fields")
    if document.get("schema") != OWNER_SEED_SCHEMA:
        raise _fail("schema")
    if document.get("schema_version") != OWNER_SEED_SCHEMA_VERSION:
        raise _fail("schema_version")
    if document.get("role") != "owner":
        raise _fail("role")
    fields = {}
    for key in ("username", "first_name", "last_name", "title"):
        value = document.get(key)
        if not isinstance(value, str):
            raise _fail(f"{key}_missing")
        fields[key] = value
    if not fields["title"].strip():
        raise _fail("title_missing")
    try:
        first, last, title, username, _ = _validate_profile(**fields)
    except ValidationError as exc:
        raise _fail(f"profile_{exc.code}") from exc
    secret = document.get("password")
    if not isinstance(secret, Mapping) or set(secret) != _DIGEST_KEYS:
        raise _fail("password_shape")
    if secret.get("algorithm") != ALGORITHM:
        raise _fail("algorithm")
    parameters = _parameters(secret.get("parameters"))
    salt = _decode(secret.get("salt"), "salt")
    derived = _decode(secret.get("hash"), "hash")
    if len(salt) < 16:
        raise _fail("salt_short")
    if len(derived) != parameters["dklen"]:
        raise _fail("hash_length")
    digest = PasswordDigest(
        algorithm=ALGORITHM,
        parameters_json=json.dumps(parameters, sort_keys=True, separators=(",", ":")),
        salt_b64=base64.b64encode(salt).decode("ascii"),
        hash_b64=base64.b64encode(derived).decode("ascii"),
    )
    return OwnerSeed(
        username=username, first_name=first, last_name=last, title=title, digest=digest
    )


def load_owner_seed(path: Path) -> OwnerSeed:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail("unreadable") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _fail("not_json") from exc
    return parse_owner_seed(document)


def seed_document(seed: OwnerSeed, *, created_at: str, generator: str) -> dict[str, Any]:
    """The file form of ``seed`` - the digest and the profile, nothing else."""
    return {
        "schema": OWNER_SEED_SCHEMA,
        "schema_version": OWNER_SEED_SCHEMA_VERSION,
        "username": seed.username,
        "first_name": seed.first_name,
        "last_name": seed.last_name,
        "title": seed.title,
        "role": "owner",
        "password": {
            "algorithm": seed.digest.algorithm,
            "parameters": json.loads(seed.digest.parameters_json),
            "salt": seed.digest.salt_b64,
            "hash": seed.digest.hash_b64,
        },
        "created_at": created_at,
        "generator": generator,
    }


def apply_owner_seed(
    identity: IdentityService, path: Optional[Path] = None
) -> SeedResult:
    """Create the packaged owner if, and only if, nobody is here yet."""
    source = Path(path) if path is not None else default_owner_seed_path()
    try:
        present = source.is_file()
    except OSError:
        present = False
    if not present:
        return SeedResult(SeedOutcome.ABSENT)
    try:
        seed = load_owner_seed(source)
    except OwnerSeedError as exc:
        logger.error(
            "Sistem Sahibi tohumu okunamadı (%s): %s",
            source,
            exc.details.get("reason", exc.code),
        )
        return SeedResult(SeedOutcome.INVALID, code=str(exc.details.get("reason", exc.code)))
    if not identity.needs_initial_setup:
        return _existing(identity, seed)
    try:
        identity.create_initial_owner_from_digest(seed.digest, **seed.profile())
    except ValidationError as exc:
        if exc.code in {"setup_already_complete", "owner_already_exists", "username_duplicate"}:
            # Someone finished the first run between the check and the write.
            return _existing(identity, seed)
        logger.error("Sistem Sahibi tohumdan oluşturulamadı: %s", exc.code)
        return SeedResult(SeedOutcome.INVALID, username=seed.username, code=exc.code)
    logger.info("Sistem Sahibi hesabı kurulum tohumundan oluşturuldu: %s", seed.username)
    return SeedResult(SeedOutcome.CREATED, username=seed.username)


def _existing(identity: IdentityService, seed: OwnerSeed) -> SeedResult:
    user = identity.repository.get_user_by_normalized_username(
        normalize_username(seed.username)
    )
    if user is not None and user.is_owner:
        return SeedResult(SeedOutcome.ALREADY_PRESENT, username=seed.username)
    logger.warning(
        "Kimlik veritabanında hesaplar var; paketteki Sistem Sahibi (%s) eklenmedi, "
        "mevcut hesaplara dokunulmadı.",
        seed.username,
    )
    return SeedResult(SeedOutcome.SKIPPED_EXISTING, username=seed.username)


__all__ = [
    "OWNER_SEED_FILE",
    "OWNER_SEED_SCHEMA",
    "OWNER_SEED_SCHEMA_VERSION",
    "OwnerSeed",
    "OwnerSeedError",
    "SeedOutcome",
    "SeedResult",
    "apply_owner_seed",
    "default_owner_seed_path",
    "load_owner_seed",
    "parse_owner_seed",
    "seed_document",
]
