"""Verify this build's ZED skeleton tables against the installed SDK.

Why this exists
---------------
:mod:`kinecapture.visualization.skeleton_spec` hard-codes the ZED joint orders
and bone lists that were read from ZED SDK 5.4 on the development machine.
Hard-coding them is what lets the whole application run - and be tested -
without the SDK installed.

The risk is that a future SDK release reorders or renames a joint. That would
not crash anything; it would quietly write data whose joint indices mean
something different from what the stored ``skeleton_spec`` claims, which is the
worst kind of failure for a dataset.

So whenever the SDK *is* present, this tool enumerates the live
``sl.BODY_*_PARTS`` and ``sl.BODY_*_BONES`` and compares them with the tables in
this build, reporting any drift. ``scripts/diagnose.ps1`` runs it as part of the
routine health check.

```powershell
python -m kinecapture.tools.verify_zed_topology
```
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from kinecapture.visualization.skeleton_spec import (
    ZED_BODY_FORMAT_SPECS,
    SkeletonSpec,
)


def _enumerate_parts(sl: Any, enum_name: str) -> Optional[list[str]]:
    """SDK part names in value order, excluding the ``LAST`` sentinel."""
    enum_cls = getattr(sl, enum_name, None)
    if enum_cls is None:
        return None
    members: list[tuple[int, str]] = []
    for name in dir(enum_cls):
        if name.startswith("_") or name == "LAST":
            continue
        value = getattr(getattr(enum_cls, name), "value", None)
        if value is None:
            return None
        members.append((int(value), name))
    members.sort()
    return [name for _value, name in members]


def _enumerate_bones(sl: Any, name: str) -> Optional[list[tuple[int, int]]]:
    bones = getattr(sl, name, None)
    if bones is None:
        return None
    try:
        return [(int(a.value), int(b.value)) for a, b in bones]
    except (AttributeError, TypeError, ValueError):
        return None


def _compare(
    spec: SkeletonSpec,
    sdk_parts: list[str],
    sdk_bones: Optional[list[tuple[int, int]]],
) -> list[str]:
    """Return a list of human-readable drift descriptions (empty when clean)."""
    problems: list[str] = []
    ours = [name.upper() for name in spec.joint_names]

    if len(ours) != len(sdk_parts):
        problems.append(
            f"Eklem sayısı farklı: bu yapıda {len(ours)}, SDK'da {len(sdk_parts)}."
        )

    for index, (mine, theirs) in enumerate(zip(ours, sdk_parts)):
        if mine != theirs:
            problems.append(
                f"Eklem {index}: bu yapıda '{mine.lower()}', SDK'da '{theirs}'."
            )

    if sdk_bones is not None:
        mine_bones = {tuple(sorted(edge)) for edge in spec.edges}
        their_bones = {tuple(sorted(edge)) for edge in sdk_bones}
        missing = their_bones - mine_bones
        extra = mine_bones - their_bones
        if missing:
            problems.append(f"SDK'da olup bu yapıda olmayan kemikler: {sorted(missing)}")
        if extra:
            problems.append(f"Bu yapıda olup SDK'da olmayan kemikler: {sorted(extra)}")
    return problems


def main() -> int:
    try:
        import pyzed.sl as sl
    except Exception as exc:
        print(
            "pyzed bu ortamda yok; iskelet tablosu doğrulaması atlandı.\n"
            f"  ({type(exc).__name__}: {exc})\n"
            "Bu bir hata değildir: uygulama ZED SDK olmadan da çalışır."
        )
        return 0

    try:
        version = sl.Camera.get_sdk_version()
    except Exception:  # pragma: no cover - broken install
        version = "bilinmiyor"
    print(f"ZED SDK {version} ile karşılaştırılıyor.\n")

    total_problems = 0
    for body_format, spec in sorted(ZED_BODY_FORMAT_SPECS.items()):
        parts = _enumerate_parts(sl, f"{body_format}_PARTS")
        if parts is None:
            print(f"[ATLA] {body_format}: bu SDK sürümünde tanımlı değil.")
            continue
        bones = _enumerate_bones(sl, f"{body_format}_BONES")
        problems = _compare(spec, parts, bones)
        if not problems:
            print(
                f"[ OK ] {body_format} -> {spec.name}: "
                f"{spec.num_joints} eklem, {len(spec.edges)} kemik eşleşiyor."
            )
            continue
        total_problems += len(problems)
        print(f"[FARK] {body_format} -> {spec.name}:")
        for problem in problems:
            print(f"         {problem}")

    print()
    if total_problems:
        print(
            f"{total_problems} farklılık bulundu. "
            "kinecapture/visualization/skeleton_spec.py dosyasındaki tablolar "
            "kurulu SDK ile uyuşmuyor.\n"
            "Bu tablolar düzeltilmeden gerçek kayıt ALINMAMALIDIR: eklem "
            "indeksleri yanlış anlamlandırılır.",
            file=sys.stderr,
        )
        return 1
    print("Bütün ZED iskelet tabloları kurulu SDK ile birebir uyuşuyor.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
