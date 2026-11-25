#!/usr/bin/env python3
"""PreToolUse guard: enforces the audit/implement phase contract deterministically.

Rules:
  1. phase == "audit"   -> deny every mutating tool (Edit/Write/NotebookEdit) and
                           every mutating Bash/PowerShell command.
  2. any phase          -> deny edits to paths listed in .arc/protected.txt.

The point: Prompt 1 says "НИЧЕГО не меняешь" and Prompt 2 says "Не трогать: <list>".
Prose in a prompt is a request; this is an enforcement. Same philosophy the prompts
themselves demand -- deterministic code beats asking the model to behave.

Reads the hook payload as JSON on stdin, replies with a PreToolUse permissionDecision.
"""

import fnmatch
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PHASE_FILE = os.path.join(ROOT, ".arc", "phase")
PROTECTED_FILE = os.path.join(ROOT, ".arc", "protected.txt")

WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

# Commands that mutate state. Matched against the command with quoted spans removed.
MUTATING_CMD = re.compile(
    r"(?:^|[;&|(]\s*)\s*(?:"
    r"rm|rmdir|mv|cp|mkdir|touch|tee|truncate|chmod|chown|ln"
    r"|sed\s+-[a-z]*i|perl\s+-[a-z]*i"
    r"|npm\s+(?:i|install|ci|uninstall|update|link|publish)"
    r"|pnpm\s+(?:i|install|add|remove|update)"
    r"|yarn\s+(?:add|remove|install|upgrade)"
    r"|pip\d?\s+(?:install|uninstall)"
    r"|python\d?\s+-m\s+pip\s+(?:install|uninstall)"
    r"|git\s+(?:commit|checkout|switch|reset|revert|restore|apply|am|clean|push"
    r"|merge|rebase|cherry-pick|stash|tag|init|add|mv|rm)"
    r"|gh\s+(?:pr\s+(?:create|merge|close|edit)|issue\s+(?:create|close|edit)|release)"
    r"|docker|docker-compose|systemctl|Set-Content|Add-Content|Out-File|Remove-Item|New-Item"
    r")\b",
    re.IGNORECASE,
)

QUOTED = re.compile(r"""'[^']*'|"[^"]*\"""")
REDIRECT = re.compile(r"(?<![0-9<>])>{1,2}(?!&)")


def read_phase() -> str:
    try:
        with open(PHASE_FILE, "r", encoding="utf-8") as fh:
            return fh.read().strip().lower()
    except OSError:
        return "off"


def read_protected() -> list:
    try:
        with open(PROTECTED_FILE, "r", encoding="utf-8") as fh:
            return [
                ln.strip()
                for ln in fh
                if ln.strip() and not ln.lstrip().startswith("#")
            ]
    except OSError:
        return []


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.exit(0)


def shell_mutates(command: str) -> str:
    """Return a human reason if the command looks mutating, else empty string."""
    stripped = QUOTED.sub("''", command)
    if REDIRECT.search(stripped):
        return "перенаправление вывода в файл (> / >>)"
    hit = MUTATING_CMD.search(stripped)
    return f"мутирующая команда `{hit.group(0).strip()}`" if hit else ""


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # never block on a malformed payload

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    phase = read_phase()

    # Rule 2: protected paths, enforced in every phase.
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if tool in WRITE_TOOLS and path:
        norm = os.path.abspath(path).replace("\\", "/")
        for pattern in read_protected():
            pat = pattern.replace("\\", "/")
            if fnmatch.fnmatch(norm, pat) or fnmatch.fnmatch(norm, f"*/{pat.lstrip('/')}"):
                deny(
                    f"{path} в списке .arc/protected.txt (совпал шаблон `{pattern}`). "
                    "Правка запрещена во всех фазах. Снять запрет может только человек, "
                    "отредактировав этот файл."
                )

    if phase != "audit":
        sys.exit(0)

    # Rule 1: audit phase is read-only everywhere except the report drop-box.
    # Writing the audit report is not "меняешь систему" — it is the deliverable.
    if tool in WRITE_TOOLS:
        reports_dir = os.path.join(ROOT, "reports").replace("\\", "/").lower()
        target = os.path.abspath(path).replace("\\", "/").lower() if path else ""
        if target.startswith(reports_dir + "/"):
            sys.exit(0)
        deny(
            f"Фаза `audit`: {tool} запрещён вне reports/ (Промпт 1, ограничение №3 — "
            "«на этом этапе НИЧЕГО не меняешь»). Отчёт пиши в reports/01-audit/. "
            "Для перехода к внедрению человек переключает .arc/phase на `implement`."
        )

    if tool in SHELL_TOOLS:
        command = tool_input.get("command", "")
        reason = shell_mutates(command)
        if reason:
            deny(
                f"Фаза `audit`: в команде обнаружено {reason} — запрещено "
                "(Промпт 1, ограничение №3). Читать (ls/cat/grep/git log/git diff/"
                "git status) можно."
            )

    sys.exit(0)


if __name__ == "__main__":
    main()
