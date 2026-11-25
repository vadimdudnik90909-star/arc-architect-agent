#!/usr/bin/env python3
"""Deterministic verification gate for Промпт 2, Шаг 3.

The prompt demands real checks, not "убедись, что работает": tests must pass,
removed components must be gone from the codebase, lint/build must exit 0, and
metrics must be compared against a baseline. This script is that gate.

It is config-driven (.arc/verify.json) so it stays honest: if the config is not
filled in, the script FAILS LOUDLY rather than reporting a green run over nothing.

Usage:
    python scripts/verify.py            # run every step
    python scripts/verify.py --step tests
    python scripts/verify.py --list

Exit code 0 = all checks passed. Anything else = do not proceed to the next plan item.
"""

import argparse
import fnmatch
import json
import os
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):  # Windows console defaults to a legacy codepage
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, ".arc", "verify.json")

OK = "PASS"
BAD = "FAIL"


def load_config():
    if not os.path.isfile(CONFIG):
        sys.exit(f"{BAD}: нет {CONFIG}. Заполни его до начала внедрения.")
    with open(CONFIG, "r", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_cwd(cfg, step):
    raw = step.get("cwd") or cfg.get("target_repo") or ROOT
    if raw.startswith("[") or not raw:
        sys.exit(
            f"{BAD}: target_repo в .arc/verify.json не заполнен (значение: {raw!r}). "
            "Проверки без репозитория бессмысленны."
        )
    path = raw if os.path.isabs(raw) else os.path.join(ROOT, raw)
    if not os.path.isdir(path):
        sys.exit(f"{BAD}: рабочая директория не существует: {path}")
    return path


def run_command_step(cfg, step):
    cmd = step.get("command", "")
    if not cmd or cmd.startswith("["):
        return BAD, f"команда не заполнена (значение: {cmd!r})"
    cwd = resolve_cwd(cfg, step)
    expect = step.get("expect_exit", 0)
    proc = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-15:]
    detail = "\n".join("      " + ln for ln in tail)
    if proc.returncode != expect:
        return BAD, f"exit {proc.returncode}, ожидался {expect}\n{detail}"
    return OK, f"exit {proc.returncode}"


# Каталоги, которые не обходим никогда: не исходники проекта.
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build", "coverage"}
# Расширения, которые считаем текстом. Всё остальное пропускаем — двоичный файл
# с совпавшей последовательностью байт не является ссылкой на компонент.
TEXT_EXT = {".mjs", ".js", ".ts", ".json", ".md", ".txt", ".yml", ".yaml", ".ps1", ".mts", ".cjs"}


def _is_allowed(rel, patterns):
    """rel — путь через '/'. Совпадение с любым шаблоном разрешает файл."""
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat):
            return True
        # "docs/**" должен покрывать и сам "docs/x.md", и вложенные уровни
        if pat.endswith("/**") and (rel == pat[:-3] or rel.startswith(pat[:-2])):
            return True
    return False


def run_grep_step(cfg, step):
    """Assert removed symbols have 0 occurrences outside the allowed paths.

    Поиск сделан на чистом Python намеренно: внешний `rg` не резолвится из
    Python на Windows (он живёт в PATH оболочки, а не процесса), и проверочный
    контур не должен падать из-за отсутствия стороннего бинарника.
    """
    symbols = [s for s in step.get("symbols", []) if s and not s.startswith("[")]
    if not symbols:
        return OK, "список удалённых символов пуст — нечего проверять"
    root = resolve_cwd(cfg, step)
    allowed = step.get("allowed_paths", [])

    hits = {s: [] for s in symbols}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in TEXT_EXT:
                continue
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root).replace("\\", "/")
            if _is_allowed(rel, allowed):
                continue
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            scanned += 1
            for i, line in enumerate(lines, 1):
                for sym in symbols:
                    if sym in line:
                        hits[sym].append(f"{rel}:{i}: {line.strip()[:100]}")

    problems = []
    for sym, found in hits.items():
        if found:
            problems.append(f"`{sym}`: {len(found)} вхождений\n" +
                            "\n".join("      " + h for h in found[:8]))
    if problems:
        return BAD, "остались ссылки на удалённые компоненты:\n" + "\n".join(problems)
    return OK, f"{len(symbols)} символов, 0 вхождений (просмотрено файлов: {scanned})"


def run_metric_step(cfg, step):
    cmd = step.get("command", "")
    if not cmd or cmd.startswith("["):
        return BAD, f"команда метрики не заполнена (значение: {cmd!r})"
    baseline = step.get("baseline")
    if baseline is None:
        return BAD, "baseline не задан — сравнивать не с чем (Промпт 2, Шаг 3)"
    cwd = resolve_cwd(cfg, step)
    proc = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return BAD, f"команда метрики упала: exit {proc.returncode}"
    try:
        value = float(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return BAD, f"вывод не число: {proc.stdout.strip()[:120]!r}"
    direction = step.get("direction", "lower_is_better")
    improved = value <= baseline if direction == "lower_is_better" else value >= baseline
    note = f"{value} vs baseline {baseline}"
    return (OK, note) if improved else (BAD, f"регресс: {note}")


RUNNERS = {"command": run_command_step, "grep_removed": run_grep_step, "metric": run_metric_step}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", help="запустить только этот шаг по имени")
    ap.add_argument("--list", action="store_true", help="показать шаги и выйти")
    args = ap.parse_args()

    cfg = load_config()
    steps = cfg.get("steps", [])
    if not steps:
        sys.exit(f"{BAD}: в .arc/verify.json нет ни одного шага.")

    if args.list:
        for s in steps:
            print(f"  {s.get('name'):<20} {s.get('type', 'command')}")
        return 0

    if args.step:
        steps = [s for s in steps if s.get("name") == args.step]
        if not steps:
            sys.exit(f"{BAD}: шаг {args.step!r} не найден.")

    failures = 0
    print(f"=== verify: {len(steps)} шаг(ов) ===")
    for step in steps:
        name = step.get("name", "<без имени>")
        runner = RUNNERS.get(step.get("type", "command"))
        if runner is None:
            status, detail = BAD, f"неизвестный тип шага {step.get('type')!r}"
        else:
            status, detail = runner(cfg, step)
        failures += status == BAD
        print(f"[{status}] {name}: {detail}")

    print(f"=== итог: {len(steps) - failures}/{len(steps)} прошли ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
