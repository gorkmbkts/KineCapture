"""Versioned password derivation built only from Python's standard library."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Mapping

from kinecapture.core.errors import ValidationError

ALGORITHM = "scrypt-v1"
DEFAULT_PARAMETERS: dict[str, int] = {
    "n": 2**14,
    "r": 8,
    "p": 1,
    "dklen": 32,
}
_MAX_MEMORY = 64 * 1024 * 1024


@dataclass(frozen=True)
class PasswordDigest:
    algorithm: str
    parameters_json: str
    salt_b64: str
    hash_b64: str


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValidationError(
            "Şifre en az 8 karakter olmalıdır.",
            field="password",
            code="password_too_short",
        )
    if len(password) > 1024:
        raise ValidationError(
            "Şifre çok uzun.", field="password", code="password_too_long"
        )


def _derive(password: str, salt: bytes, parameters: Mapping[str, int]) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=int(parameters["n"]),
        r=int(parameters["r"]),
        p=int(parameters["p"]),
        dklen=int(parameters["dklen"]),
        maxmem=_MAX_MEMORY,
    )


def hash_password(password: str) -> PasswordDigest:
    validate_password(password)
    salt = secrets.token_bytes(16)
    parameters = dict(DEFAULT_PARAMETERS)
    derived = _derive(password, salt, parameters)
    return PasswordDigest(
        algorithm=ALGORITHM,
        parameters_json=json.dumps(parameters, sort_keys=True, separators=(",", ":")),
        salt_b64=base64.b64encode(salt).decode("ascii"),
        hash_b64=base64.b64encode(derived).decode("ascii"),
    )


def verify_password(
    password: str,
    *,
    algorithm: str,
    parameters_json: str,
    salt_b64: str,
    hash_b64: str,
) -> bool:
    if algorithm != ALGORITHM:
        return False
    try:
        parameters = json.loads(parameters_json)
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
        actual = _derive(password, salt, parameters)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return secrets.compare_digest(actual, expected)


__all__ = [
    "ALGORITHM",
    "DEFAULT_PARAMETERS",
    "PasswordDigest",
    "hash_password",
    "validate_password",
    "verify_password",
]
