#!/usr/bin/env python3
"""Snapshot the installed plugin marketplaces into a searchable local catalog.

Why this exists: Промпт 1, Шаг 3 requires searching for ready-made solutions and
FORBIDS inventing plugin names ("Названия и ссылки — только реально найденные").
A local snapshot is the ground truth the auditor greps instead of recalling from
memory. Re-run it before every audit so the catalog is current.

Usage:  python scripts/snapshot_marketplace.py
Output: reference/marketplace-catalog.md
"""

import datetime
import json
import os
import sys

for _stream in (sys.stdout, sys.stderr):  # Windows console defaults to a legacy codepage
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKETPLACES = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "marketplaces")
OUT = os.path.join(ROOT, "reference", "marketplace-catalog.md")


def collect():
    rows = []
    if not os.path.isdir(MARKETPLACES):
        return rows
    for market in sorted(os.listdir(MARKETPLACES)):
        manifest = os.path.join(MARKETPLACES, market, ".claude-plugin", "marketplace.json")
        if not os.path.isfile(manifest):
            continue
        with open(manifest, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for plugin in data.get("plugins", []):
            rows.append(
                {
                    "marketplace": market,
                    "name": plugin.get("name", ""),
                    "description": (plugin.get("description") or "").replace("|", "\\|").replace("\n", " "),
                    "version": plugin.get("version", ""),
                }
            )
    return rows


def main():
    rows = collect()
    if not rows:
        print("Маркетплейсы не найдены в " + MARKETPLACES, file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    markets = sorted({r["marketplace"] for r in rows})

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("# Каталог готовых решений (снимок)\n\n")
        fh.write(f"Сгенерировано `scripts/snapshot_marketplace.py` — {stamp}.\n")
        fh.write("**Не редактировать вручную.** Перегенерировать перед каждым аудитом.\n\n")
        fh.write(f"Источники: {', '.join('`' + m + '`' for m in markets)}. ")
        fh.write(f"Всего плагинов: **{len(rows)}**.\n\n")
        fh.write("> Это единственный разрешённый источник названий плагинов при ответе\n")
        fh.write("> на Шаг 3 Промпта 1. Чего нет здесь и не подтверждено WebFetch/gh —\n")
        fh.write("> того не существует; писать «готового решения не найдено».\n\n")
        fh.write("| Плагин | Маркетплейс | Описание |\n|---|---|---|\n")
        for r in sorted(rows, key=lambda x: x["name"]):
            fh.write(f"| `{r['name']}` | {r['marketplace']} | {r['description']} |\n")

    print(f"OK: {len(rows)} плагинов -> {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
