"""Make the installer's System Owner seed - on the owner's own terminal.

Run it yourself, in a real console (Windows Terminal, PowerShell, cmd):

    C:\\Users\\<you>\\anaconda3\\envs\\KineSynth\\python.exe scripts\\release\\make_owner_seed.py --title "<unvan>"

It asks for the password twice with ``getpass`` (nothing is echoed), checks
the same rules the application enforces, and writes only the ``scrypt-v1``
digest - algorithm, parameters, salt, hash - with the owner's profile to
``dist/owner_seed.json``. The password is never taken from an argument, an
environment variable or a file, and is never written or printed; neither is
the digest. ``dist/`` is ignored by git, and so is any ``owner_seed.json``.

``scripts/release/build_installer.ps1`` puts the file into the installer; see
``kinecapture.identity.seed`` for what the application does with it.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from kinecapture import APP_VERSION  # noqa: E402
from kinecapture.core.errors import ValidationError  # noqa: E402
from kinecapture.core.ids import utc_now_iso  # noqa: E402
from kinecapture.core.jsonio import write_json  # noqa: E402
from kinecapture.identity.passwords import (  # noqa: E402
    hash_password,
    validate_password,
    verify_password,
)
from kinecapture.identity.seed import (  # noqa: E402
    OWNER_SEED_FILE,
    OwnerSeed,
    OwnerSeedError,
    load_owner_seed,
    parse_owner_seed,
    seed_document,
)

#: Fixed by the owner's decision of 23 September 2026; only the title is asked.
DEFAULT_USERNAME = "gorkembektas"
DEFAULT_FIRST_NAME = "Görkem"
DEFAULT_LAST_NAME = "Bektaş"
ALLOWED_PARENTS = ("dist", "build")


def _output_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO / path
    path = path.resolve()
    parents = [(REPO / name).resolve() for name in ALLOWED_PARENTS]
    if not any(parent == path.parent or parent in path.parents for parent in parents):
        raise SystemExit(
            f"Tohum yalnız derleme çıktısına yazılır ({', '.join(ALLOWED_PARENTS)}/); "
            f"verilen yol: {path}"
        )
    return path


def _ask_password(prompt=getpass.getpass) -> str:  # noqa: ANN001 - injectable for tests
    first = prompt("Sistem Sahibi parolası: ")
    try:
        validate_password(first)
    except ValidationError as exc:
        raise SystemExit(f"Parola kabul edilmedi: {exc.message}") from None
    second = prompt("Parola (tekrar): ")
    if first != second:
        raise SystemExit("Parolalar eşleşmedi; hiçbir dosya yazılmadı.")
    return first


def make_seed(
    out: Path,
    *,
    username: str,
    first_name: str,
    last_name: str,
    title: str,
    prompt=getpass.getpass,  # noqa: ANN001
) -> OwnerSeed:
    if not title.strip():
        raise SystemExit("Unvan zorunludur (--title).")
    password = _ask_password(prompt)
    digest = hash_password(password)
    seed = OwnerSeed(
        username=username, first_name=first_name, last_name=last_name, title=title,
        digest=digest,
    )
    try:
        document = seed_document(
            seed, created_at=utc_now_iso(), generator=f"make_owner_seed.py {APP_VERSION}"
        )
        seed = parse_owner_seed(document)  # the same checks the application runs
    except OwnerSeedError as exc:
        raise SystemExit(f"Tohum oluşturulamadı: {exc.details.get('reason', exc.code)}") from None
    write_json(out, document, overwrite=True)
    written = load_owner_seed(out)
    if not verify_password(
        password,
        algorithm=written.digest.algorithm,
        parameters_json=written.digest.parameters_json,
        salt_b64=written.digest.salt_b64,
        hash_b64=written.digest.hash_b64,
    ):
        out.unlink(missing_ok=True)
        raise SystemExit("Yazılan tohum doğrulanamadı; dosya silindi.")
    del password
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--title", default=None, help="Unvan (zorunlu; verilmezse sorulur)")
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--first-name", default=DEFAULT_FIRST_NAME)
    parser.add_argument("--last-name", default=DEFAULT_LAST_NAME)
    parser.add_argument("--out", default=str(Path("dist") / OWNER_SEED_FILE))
    args = parser.parse_args(argv)
    out = _output_path(args.out)
    title = args.title if args.title is not None else input("Unvan: ")
    seed = make_seed(
        out,
        username=args.username,
        first_name=args.first_name,
        last_name=args.last_name,
        title=title,
    )
    print(f"Tohum yazıldı: {out}")
    print(f"Sistem Sahibi: {seed.username} ({seed.first_name} {seed.last_name}, {seed.title})")
    print("Parola ve parola özeti ekrana yazılmadı. Şimdi kurucuyu derleyin:")
    print("  powershell -ExecutionPolicy Bypass -File scripts\\release\\build_installer.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
