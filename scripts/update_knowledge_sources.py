"""Refresh compact Obsidian source registries without copying raw transcripts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "knowledge" / "sources"
CLAUDE_PROJECT = Path.home() / ".claude" / "projects" / "C--Users-gorke-Desktop-KineCapture"
CODEX_ROOTS = [Path.home() / ".codex" / "sessions", Path.home() / ".codex" / "archived_sessions"]
MAX_EXCERPT = 260


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(text: str) -> str:
    text = re.sub(r"<recommended_plugins>[\s\S]*?</recommended_plugins>", "", text)
    text = re.sub(r"# AGENTS\.md instructions[\s\S]*?</INSTRUCTIONS>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_EXCERPT:
        text = text[: MAX_EXCERPT - 1].rstrip() + "…"
    return text.replace("|", "\\|")


def claude_message_text(message: object) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return " ".join(
        str(part.get("text", ""))
        for part in content
        if isinstance(part, dict) and part.get("type") == "text"
    )


def jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def claude_sessions() -> list[dict[str, object]]:
    rows = []
    if not CLAUDE_PROJECT.exists():
        return rows
    for path in sorted(CLAUDE_PROJECT.glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        titles: list[str] = []
        prompts: list[str] = []
        for item in jsonl(path):
            if item.get("type") in {"custom-title", "ai-title"}:
                value = item.get("customTitle") or item.get("aiTitle") or item.get("title")
                if value and value not in titles:
                    titles.append(value)
            if item.get("type") == "last-prompt":
                value = item.get("lastPrompt")
                if value and value not in prompts:
                    prompts.append(value)
            if item.get("type") == "user" and item.get("toolUseResult") is None:
                origin = item.get("origin")
                if isinstance(origin, dict) and origin.get("kind") == "task-notification":
                    continue
                value = claude_message_text(item.get("message"))
                if value and value not in prompts:
                    prompts.append(value)
        stat = path.stat()
        rows.append(
            {
                "id": path.stem,
                "path": path,
                "bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "sha": sha256(path),
                "title": clean(titles[-1] if titles else "Claude Code session"),
                "prompts": [clean(value) for value in prompts if clean(value)],
            }
        )
    return rows


def message_text(payload: dict[str, object]) -> str:
    parts = []
    for part in payload.get("content", []) if isinstance(payload.get("content"), list) else []:
        if isinstance(part, dict) and part.get("type") in {"input_text", "text"}:
            parts.append(str(part.get("text", "")))
    return " ".join(parts)


def codex_sessions() -> list[dict[str, object]]:
    candidates: set[Path] = set()
    for base in CODEX_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*.jsonl"):
            try:
                if b"kinecapture" in path.read_bytes().lower():
                    candidates.add(path)
            except OSError:
                continue
    rows = []
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime):
        prompts: list[str] = []
        cwd = ""
        session_id = path.stem
        for item in jsonl(path):
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if item.get("type") == "session_meta":
                cwd = str(payload.get("cwd", ""))
                session_id = str(payload.get("id") or payload.get("session_id") or session_id)
            if item.get("type") != "response_item" or payload.get("type") != "message":
                continue
            if payload.get("role") != "user":
                continue
            metadata = payload.get("internal_chat_message_metadata_passthrough")
            kinds = metadata.get("content_item_kinds", []) if isinstance(metadata, dict) else []
            if kinds and "user.text" not in kinds:
                continue
            value = clean(message_text(payload))
            if not value or value.startswith("<recommended_plugins>"):
                continue
            if value not in prompts:
                prompts.append(value)
        relevant = "kinecapture" in cwd.lower() or any(
            "kinecapture" in prompt.lower() or "kinesynth" in prompt.lower()
            for prompt in prompts
        )
        if not relevant:
            continue
        stat = path.stat()
        rows.append(
            {
                "id": session_id,
                "file": path.name,
                "path": path,
                "cwd": cwd,
                "bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "sha": sha256(path),
                "prompts": prompts,
            }
        )
    return rows


def write_conversations(claude: list[dict[str, object]], codex: list[dict[str, object]]) -> None:
    lines = [
        "---",
        "type: source-registry",
        "status: generated",
        f"updated: {datetime.now().date().isoformat()}",
        "---",
        "",
        "# Konuşma sicili",
        "",
        "Ham oturumlar kopyalanmaz veya AI başlangıç bağlamına alınmaz. Bu sicil",
        "kaynağı eksiksiz tanımlar; kalıcı ve doğrulanmış bilgi konu notlarına taşınır.",
        "Boyut, değişiklik zamanı ve SHA-256 sicil yenileme anındaki anlık görüntüdür;",
        "aktif bir oturum sonraki mesajlarla doğal olarak değişebilir.",
        "",
        f"- Claude Code JSONL: **{len(claude)}**",
        f"- Codex JSONL: **{len(codex)}**",
        f"- Toplam kaynak boyutu: **{sum(int(x['bytes']) for x in claude + codex):,} bayt**",
        "",
        "## Claude Code",
        "",
    ]
    for row in claude:
        lines += [
            f"### {row['title'] or row['id']}",
            "",
            f"- Oturum: `{row['id']}`",
            f"- Değişiklik: `{row['modified']}`",
            f"- Boyut: `{row['bytes']}` bayt",
            f"- SHA-256: `{row['sha']}`",
            f"- Yerel kaynak: `{row['path']}`",
            "- Benzersiz kullanıcı istemleri:",
        ]
        prompts = row["prompts"]
        lines += [f"  - {value}" for value in prompts] if prompts else ["  - Başlık dışında kısa istem bulunamadı."]
        lines.append("")
    lines += ["## Codex", ""]
    for row in codex:
        lines += [
            f"### {row['id']}",
            "",
            f"- Oturum dosyası: `{row['file']}`",
            f"- Değişiklik: `{row['modified']}`",
            f"- Çalışma klasörü: `{row['cwd'] or 'bilinmiyor'}`",
            f"- Boyut: `{row['bytes']}` bayt",
            f"- SHA-256: `{row['sha']}`",
            f"- Yerel kaynak: `{row['path']}`",
            "- Benzersiz kullanıcı istemleri:",
        ]
        prompts = row["prompts"]
        lines += [f"  - {value}" for value in prompts] if prompts else ["  - Kısa kullanıcı istemi çıkarılamadı."]
        lines.append("")
    (OUT / "conversation-registry.md").write_text("\n".join(lines), encoding="utf-8")


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def write_git_history() -> int:
    raw = git_output("log", "--reverse", "--date=short", "--pretty=format:%h|%ad|%s")
    commits = [line.split("|", 2) for line in raw.splitlines() if line]
    lines = [
        "---",
        "type: milestone-index",
        "status: generated",
        f"updated: {datetime.now().date().isoformat()}",
        "---",
        "",
        "# Git kilometre taşları",
        "",
        "Git değişikliğin kesin kaydıdır; bu liste neden ve deney bağlamına giden",
        "kronolojik giriş noktasıdır.",
        "",
        "| Tarih | Commit | Mesaj |",
        "|---|---|---|",
    ]
    for commit, date, subject in commits:
        lines.append(f"| {date} | `{commit}` | {subject.replace('|', '&#124;')} |")
    (ROOT / "knowledge" / "milestones" / "git-history.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(commits)


def write_documents() -> dict[str, int]:
    root_docs = sorted(path for path in ROOT.glob("*.md") if path.is_file())
    prompt_docs = sorted(
        path for path in (ROOT / "promts").glob("*.md")
        if path.is_file() and path.name != "index.md"
    )
    report_docs = sorted(
        path for path in (ROOT / "knowledge" / "archive" / "reports").glob("*.md")
        if path.is_file() and path.name != "index.md"
    )
    docs = [*root_docs, *prompt_docs, *report_docs]
    roles = {
        "AGENTS.md": "Codex ortak talimatı",
        "CLAUDE.md": "Claude giriş ve ortak talimat içe aktarımı",
        "MEMORY_INDEX.md": "Kısa AI yönlendiricisi",
        "MEMORY.md": "Kısa uyumluluk yönlendiricisi",
        "README.md": "Kullanıcı ve geliştirici başlangıç belgesi",
    }
    lines = [
        "---",
        "type: source-registry",
        "status: generated",
        f"updated: {datetime.now().date().isoformat()}",
        "---",
        "",
        "# Belge sicili",
        "",
        "Kökteki temel belgeler ile taşınmış prompt ve rapor kaynaklarını listeler.",
        "Büyük tarihsel belgeler yalnız ilgili kaynak araştırmasında açılır.",
        "",
        "| Belge | Bayt | Rol |",
        "|---|---:|---|",
    ]
    for path in docs:
        if path.parent == ROOT / "promts":
            role = "Tarihsel görev promptu"
        elif path.parent == ROOT / "knowledge" / "archive" / "reports":
            role = "Tarihsel plan veya rapor"
        else:
            role = roles.get(path.name, "Temel repository belgesi")
        relative = path.relative_to(ROOT).as_posix().replace(" ", "%20")
        lines.append(f"| [{path.name}](../../{relative}) | {path.stat().st_size} | {role} |")
    (OUT / "document-registry.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "root": len(root_docs),
        "prompts": len(prompt_docs),
        "reports": len(report_docs),
        "total": len(docs),
    }


def write_source_summary(
    claude_count: int,
    codex_count: int,
    docs: dict[str, int],
    commits: int,
) -> None:
    memory_parts = len(
        [
            path
            for path in (ROOT / "knowledge" / "archive" / "memory").glob("*.md")
            if path.name != "index.md"
        ]
    )
    text = f"""---
type: source-registry
status: current
updated: {datetime.now().date().isoformat()}
---

# Kaynak sicili

Bu sayfa kalıcı bilginin hangi ham kayıtlardan türetilebileceğini gösterir.
Kaynakların tamamı başlangıç bağlamına yüklenmez.

| Kaynak | Sayı | Ayrıntı |
|---|---:|---|
| Kök temel Markdown belgeleri | {docs['root']} | [Belge sicili](document-registry.md) |
| Tarihsel görev promptları | {docs['prompts']} | [Prompt arşivi](../../promts/index.md) |
| Tarihsel plan ve raporlar | {docs['reports']} | [Rapor arşivi](../archive/reports/index.md) |
| Git commitleri | {commits} | [Git kilometre taşları](../milestones/git-history.md) |
| Claude Code oturumları | {claude_count} | [Konuşma sicili](conversation-registry.md) |
| Codex oturumları | {codex_count} | [Konuşma sicili](conversation-registry.md) |
| Tarihsel hafıza mini notları | {memory_parts} | [Bölünmüş MEMORY arşivi](../archive/memory/index.md) |

Ham JSONL kaynakları kullanıcı profilindeki özgün konumlarında bırakılmıştır.
Sicilde tam konum, boyut ve SHA-256 bulunduğundan kaynak kimliği korunur;
tekrarlarla dolu yüzlerce MB veri repository'ye kopyalanmaz.
"""
    (OUT / "source-registry.md").write_text(text, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / "knowledge" / "milestones").mkdir(parents=True, exist_ok=True)
    claude = claude_sessions()
    codex = codex_sessions()
    write_conversations(claude, codex)
    commits = write_git_history()
    docs = write_documents()
    write_source_summary(len(claude), len(codex), docs, commits)
    print(
        json.dumps(
            {
                "claude": len(claude),
                "codex": len(codex),
                "documents": docs["total"],
                "root_documents": docs["root"],
                "prompts": docs["prompts"],
                "reports": docs["reports"],
                "commits": commits,
            }
        )
    )


if __name__ == "__main__":
    main()
