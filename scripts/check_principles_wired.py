#!/usr/bin/env python3
"""Проверка: базовые принципы (03_*, 04_*) действительно попадают в промпт.

Зачем код, а не правило в CLAUDE.md. Канонические промпты 01/02 править нельзя
(запрет хука), поэтому принципы подставляются в промпт композицией — ссылками
`@03_…` и `@04_…` из файлов команд. У такой схемы есть тихий режим отказа: кто-то
правит команду, ссылка теряется, команды продолжают работать, отчёты продолжают
выходить — просто без принципов, и по тексту отчёта этого не видно.

Ровно тот же дефект уже дважды случился в целевой системе («код есть, промпт о нём
не знает»), и лечится он одинаково: проверкой, а не памятью.

Запуск: python scripts/check_principles_wired.py     # exit 0 = подключены
"""

import os
import sys

for _stream in (sys.stdout, sys.stderr):  # Windows console defaults to a legacy codepage
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Файл принципов -> минимальный размер, ниже которого это заготовка, а не инструкция.
PRINCIPLES = {
    "03_oop_principles_for_agent_architecture.md": 2000,
    "04_solid_principles_for_agent_architecture.md": 2000,
}

# Где ссылка обязана присутствовать. Команды — это и есть «базовый промпт»:
# именно их текст уходит модели вместе с каноном.
CONSUMERS = [
    os.path.join(".claude", "commands", "arc-audit.md"),
    os.path.join(".claude", "commands", "arc-implement.md"),
    "CLAUDE.md",
]

PLACEHOLDER = "[ЗАПОЛНИТЬ"


def read(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def main():
    problems = []

    for name, min_size in PRINCIPLES.items():
        body = read(name)
        if body is None:
            problems.append(f"{name}: файла нет — ссылки в командах ведут в пустоту")
            continue
        size = len(body.encode("utf-8"))
        if size < min_size:
            problems.append(f"{name}: {size} байт (< {min_size}) — похоже на заготовку")
        if PLACEHOLDER in body:
            problems.append(f"{name}: остались метки {PLACEHOLDER}…] — инструкция не дописана")
        if "## Чеклист аудита" not in body:
            problems.append(f"{name}: нет раздела «## Чеклист аудита» — по чему тогда проверять компонент")

    for rel in CONSUMERS:
        body = read(rel)
        if body is None:
            problems.append(f"{rel}: файла нет")
            continue
        for name in PRINCIPLES:
            # В командах нужна именно @-ссылка (она подставляет текст в промпт);
            # в CLAUDE.md достаточно упоминания файла.
            needed = f"@{name}" if rel.startswith(".claude") else name
            if needed not in body:
                problems.append(f"{rel}: нет ссылки «{needed}» — принципы в этот прогон не попадут")

    if problems:
        print("FAIL: базовые принципы подключены не полностью")
        for p in problems:
            print(f"  - {p}")
        print("\nПочинить = вернуть ссылку/файл, а не убрать проверку.")
        return 1

    print(f"PASS: принципы ({len(PRINCIPLES)}) подключены во всех точках ({len(CONSUMERS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
