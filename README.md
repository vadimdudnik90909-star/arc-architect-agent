# ARC — архитектурный агент

Инструкции и инструменты аудита, проектирования и внедрения архитектуры агентов.
Канонические промпты 01/02 и принципы ООП/SOLID 03/04 сохранены из текущей рабочей версии.

## Состав

- `01_agent_architect_audit.md`, `02_agent_architect_implement.md` — аудит, план оптимизации и внедрение.
- `03_oop_principles_for_agent_architecture.md`, `04_solid_principles_for_agent_architecture.md` — обязательные принципы проектирования.
- `CLAUDE.md`, `.claude/commands/`, `.claude/hooks/` — инструкции, команды и ограничитель фаз Claude Code.
- `scripts/` — проверки принципов, сообщений коммитов, результатов внедрения и снимок каталога плагинов.
- `.arc/` — стартовая фаза аудита, защищённые пути и шаблон проверок.
- `templates/input/` — пустые шаблоны новой задачи.

Требования: Python 3.10+ (стандартная библиотека), Git CLI; Claude Code для команд и хуков.

## Начало работы

В PowerShell из корня репозитория:

```powershell
New-Item -ItemType Directory -Force input, reports, reference
Copy-Item templates/input/* input/
python scripts/check_principles_wired.py
python scripts/verify.py --step principles-wired
```

Заполнить `input/`: целевой репозиторий, ТЗ, ограничения и проверки.
При необходимости в `.claude/settings.local.json` настроить `permissions.additionalDirectories` для доступа к целевому репозиторию.
В `.arc/verify.json` заполнить путь цели и команды её проверок; в `.arc/protected.txt` добавить защищённые пути задачи.
Полный запуск проверок намеренно завершается ошибкой до заполнения `target-tests`.

Запустить `/arc-audit` в Claude Code. Результат: `reports/01-audit/audit-report.md`.
После согласования человек сохраняет план в `reports/01-audit/approved-plan.md`, переключает `.arc/phase` на `implement` и запускает `/arc-implement`.
Файл фазы меняет человек. Перед новой задачей возвращать `audit`.

Проекты, заполненные входы, отчёты, локальные сервисы, секреты и результаты исключены из Git.
Новая история не содержит историю задач исходной машины.
Исходный `ARCHITECTURE.md` исключён: он описывает выполненный почтовый проект.
Перед коммитами `.arc/` проверять diff: настройки конкретной задачи не должны подменять переносимые шаблоны.
