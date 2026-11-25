#!/usr/bin/env python3
"""Проверка сообщения коммита: осмысленный заголовок + ссылка на ТЗ и версию.

Зачем код. Требование «пиши осмысленные сообщения» невыполнимо на дисциплине: в
конце длинной итерации сообщение пишется последним и первым же деградирует до
«правки». Здесь оно проверяется механически — как фаза в phase_guard.py.

Что требуется от сообщения:
  1. Заголовок — не мусорный («fix», «wip», «правки», «update»), длиной 10..72.
  2. Строка `ТЗ: <путь> — пункт <N> ...` — путь должен существовать на диске.
     Допустимая альтернатива: `ТЗ: вне ТЗ — <причина>` (баг-фикс по пути).
  3. Строка `Версия: ...` — версия целевой системы либо номер итерации ARC.

Запуск:
    python scripts/check_commit_message.py --last          # последний коммит HEAD
    python scripts/check_commit_message.py --file MSG      # файл с сообщением
    python scripts/check_commit_message.py --last --repo d:/CLAUDE_CODE/PROJECT1

Установка как commit-msg хук в целевом репозитории (локально, не версионируется):
    # d:/CLAUDE_CODE/PROJECT1/.git/hooks/commit-msg
    #!/bin/sh
    python "d:/CLAUDE_CODE/PROJECT3 - ARC/scripts/check_commit_message.py" --file "$1"

Exit 0 = сообщение годное. Иначе — перечень того, чего не хватает.
"""

import argparse
import os
import re
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):  # Windows console defaults to a legacy codepage
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Заголовки, которые не сообщают ничего. Проверяется всё слово, а не подстрока:
# «fix» запрещён, «fix(sort): …» — нет, там есть предмет.
JUNK_SUBJECT = re.compile(
    r"^(?:fix|update|updates|wip|tmp|temp|misc|правк[аи]|обновление|мелочи|"
    r"изменения|доработк[аи]|рефакторинг)\.?$",
    re.IGNORECASE,
)

TZ_LINE = re.compile(r"^ТЗ:\s*(.+)$", re.MULTILINE)
VERSION_LINE = re.compile(r"^Версия:\s*(.+)$", re.MULTILINE)
TZ_OUT_OF_SCOPE = re.compile(r"^вне\s+ТЗ\s*[—\-–]\s*\S+", re.IGNORECASE)
# «input/01_tz_v2.md — пункт 2 «Генератор…»» / «... — пункты 1,3»
TZ_WITH_ITEM = re.compile(r"^(\S+\.md)\s*[—\-–]\s*пункт\w*\s*([\d,\s\-–]+)")

MIN_SUBJECT = 10
MAX_SUBJECT = 72


def message_from_git(repo):
    proc = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=repo,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.exit(f"FAIL: не удалось прочитать последний коммит в {repo}: {proc.stderr.strip()}")
    return proc.stdout


def strip_comments(text):
    """Убрать строки, которые git сам выкидывает (### и т.п. из шаблона)."""
    return "\n".join(ln for ln in text.splitlines() if not ln.startswith("#"))


def check(message, repo):
    problems = []
    lines = [ln for ln in strip_comments(message).splitlines()]
    subject = lines[0].strip() if lines else ""

    if not subject:
        problems.append("пустой заголовок")
    elif JUNK_SUBJECT.match(subject):
        problems.append(f"заголовок «{subject}» ничего не сообщает — что именно изменилось и зачем")
    elif len(subject) < MIN_SUBJECT:
        problems.append(f"заголовок короче {MIN_SUBJECT} символов: «{subject}»")
    elif len(subject) > MAX_SUBJECT:
        problems.append(f"заголовок длиннее {MAX_SUBJECT} символов ({len(subject)}) — вынеси подробности в тело")

    if len(lines) > 1 and lines[1].strip():
        problems.append("после заголовка нужна пустая строка (иначе тело склеивается с ним)")

    tz = TZ_LINE.search(message)
    if not tz:
        problems.append("нет строки «ТЗ: <файл> — пункт <N> «<название>»» "
                        "(или «ТЗ: вне ТЗ — <причина>»)")
    else:
        value = tz.group(1).strip()
        if TZ_OUT_OF_SCOPE.match(value):
            pass  # работа вне ТЗ разрешена, но причина названа — этого достаточно
        else:
            m = TZ_WITH_ITEM.match(value)
            if not m:
                problems.append(f"строка ТЗ не разобрана: «{value}». Нужно "
                                "«<путь к .md> — пункт <N> «<название>»»")
            else:
                rel = m.group(1)
                # Путь ищем и в этом репозитории, и в том, где делается коммит.
                if not any(os.path.isfile(os.path.join(base, rel)) for base in (ROOT, repo)):
                    problems.append(f"ТЗ-файл «{rel}» не найден ни в {ROOT}, ни в {repo} — "
                                    "ссылка на несуществующее ТЗ хуже отсутствия ссылки")

    ver = VERSION_LINE.search(message)
    if not ver:
        problems.append("нет строки «Версия: <mail-agent X.Y.Z | ARC итерация N> (в работе | итог)»")
    elif not re.search(r"\d", ver.group(1)):
        problems.append(f"в строке версии нет ни одной цифры: «{ver.group(1).strip()}»")

    return problems


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--last", action="store_true", help="проверить последний коммит")
    src.add_argument("--file", help="файл с сообщением (для commit-msg хука)")
    ap.add_argument("--repo", default=os.getcwd(), help="репозиторий (по умолчанию cwd)")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            message = fh.read()
    else:
        message = message_from_git(repo)

    problems = check(message, repo)
    if problems:
        print("FAIL: сообщение коммита не годится")
        for p in problems:
            print(f"  - {p}")
        print("\nФормат — CLAUDE.md, раздел «Коммиты».")
        return 1

    print("PASS: заголовок осмысленный, ТЗ и версия указаны")
    return 0


if __name__ == "__main__":
    sys.exit(main())
