# Техническое задание: `model_agent_test_v11.py`

## 1. Назначение

Разработать отдельный тестовый скрипт `model_agent_test_v11.py` для проверки **агентских возможностей локальных Ollama-моделей**.

Текущий `model_performance_test_v10.py` проверяет single-shot coding prompts: модель получает один prompt и возвращает один ответ. Новый скрипт должен проверять именно agent workflow:

```text
прочитать проект → понять задачу → изменить файлы → запустить команды/тесты → увидеть ошибку → исправить → завершить задачу
```

Скрипт не должен выставлять автоматические оценки качества. Он должен собирать только факты, чтобы потом любой ИИ или человек мог проанализировать результаты.

---

## 2. Цели

Главная цель — понять, какие локальные CPU-модели Ollama реально пригодны для работы как coding agent в Cline/Roo Code/OpenHands-подобном сценарии.

Скрипт должен измерять:

1. Может ли модель работать пошагово.
2. Может ли модель читать файлы проекта.
3. Может ли модель изменять файлы.
4. Может ли модель запускать тесты/команды.
5. Может ли модель исправлять ошибки после неудачных тестов.
6. Сколько шагов ей нужно.
7. Сколько времени занимает задача.
8. Какие файлы были изменены.
9. Прошла ли итоговая проверка.
10. Насколько стабильно модель завершает задачу.

---

## 3. Что НЕ должен делать скрипт

Скрипт не должен:

1. Ставить баллы качества.
2. Самостоятельно объявлять модель "хорошей" или "плохой".
3. Давать итоговый рейтинг моделей.
4. Запускать команды вне sandbox/workspace.
5. Давать модели прямой доступ ко всей файловой системе.
6. Выполнять опасные команды.
7. Удалять пользовательские файлы.
8. Перезаписывать старые отчёты.
9. Требовать платные API.
10. Требовать GPU.

---

## 4. Основной принцип работы

Для каждой модели и каждого агентского теста скрипт должен:

1. Создать временный workspace.
2. Скопировать туда стартовые файлы тестового проекта.
3. Передать модели задачу и список доступных инструментов.
4. Запустить agent loop.
5. На каждом шаге получить от модели действие в JSON.
6. Выполнить разрешённое действие.
7. Вернуть результат действия обратно модели.
8. Повторять до `finish` или до достижения лимита шагов.
9. Запустить финальную проверку.
10. Сохранить полный transcript и факты в Markdown-отчёт.

---

## 5. Режимы запуска

```powershell
py .\model_agent_test_v11.py --agent-full
py .\model_agent_test_v11.py --agent-test agent_bugfix_file_edit
py .\model_agent_test_v11.py --model qwen2.5-coder:3b --agent-test agent_bugfix_file_edit
py .\model_agent_test_v11.py --model qwen2.5-coder:3b --agent-full
py .\model_agent_test_v11.py --list-agent-tests
py .\model_agent_test_v11.py --rerun-existing
py .\model_agent_test_v11.py --max-agent-steps 20
```

---

## 6. Выходные файлы

Скрипт должен создавать/дописывать:

```text
model_agent_test.log
model_agent_ai_report.md
agent_runs/
```

### 6.1. `model_agent_test.log`

Технический лог выполнения.

Должен содержать:

```text
timestamp
RUN_ID
MODEL
AGENT_TEST_ID
STEP
EVENT_TYPE
MESSAGE
```

Примеры событий:

```text
START
OLLAMA_API_OK
WORKSPACE_CREATED
AGENT_STEP_START
TOOL_CALL
TOOL_RESULT
COMMAND_RUN
COMMAND_RESULT
FINAL_CHECK_START
FINAL_CHECK_END
FINISH
ERROR
TIMEOUT
MAX_STEPS_REACHED
```

### 6.2. `model_agent_ai_report.md`

Главный отчёт для анализа любым ИИ.

Должен содержать:

```text
RUN_ID
AGENT_TEST_ID
PROMPT_ID
CONFIG_ID
MODEL
workspace path
duration_sec
agent_steps_count
tool_calls_count
read_file_count
write_file_count
run_command_count
files_changed
final_status
final_check_exit_code
stdout/stderr проверок
полный agent transcript
workspace diff
```

### 6.3. `agent_runs/`

Папка с фактическими workspace-запусками.

Структура:

```text
agent_runs/
  RUN-YYYYMMDD-HHMMSS-ABCDEFGH/
    model_name_safe/
      agent_test_id/
        workspace/
        transcript.jsonl
        final_diff.patch
        command_logs/
```

---

## 7. Идентификаторы

### 7.1. RUN_ID

Формат:

```text
RUN-YYYYMMDD-HHMMSS-XXXXXXXX
```

### 7.2. PROMPT_ID

Стабильный SHA-256 от нормализованного текста задачи.

Формат:

```text
PROMPT-16_HEX_SYMBOLS
```

### 7.3. CONFIG_ID

Стабильный SHA-256 от конфигурации генерации:

```json
{
  "ollama_url": "http://localhost:11434",
  "num_ctx": 4096,
  "num_predict": 1000,
  "temperature": 0.1,
  "timeout_seconds": 900,
  "max_agent_steps": 20
}
```

### 7.4. AGENT_RUN_KEY

Для пропуска уже выполненных тестов использовать ключ:

```text
model_name + agent_test_id + prompt_id + config_id
```

---

## 8. Agent loop

### 8.1. Формат ответа модели

Модель должна отвечать строго JSON-объектом.

Пример:

```json
{
  "thought_summary": "Нужно посмотреть структуру проекта и открыть app.py.",
  "tool": "list_dir",
  "args": {
    "path": "."
  }
}
```

### 8.2. Разрешённые tools

Поддержать минимум:

```text
list_dir
read_file
write_file
append_file
run_command
finish
```

### 8.3. Tool: `list_dir`

Вход:

```json
{
  "path": "."
}
```

Выход:

```json
{
  "ok": true,
  "entries": [
    {"name": "app.py", "type": "file", "size": 1200},
    {"name": "tests", "type": "dir", "size": null}
  ]
}
```

Ограничения:

- путь только внутри workspace;
- запрещён выход через `..`;
- запрещены абсолютные пути вне workspace.

### 8.4. Tool: `read_file`

Вход:

```json
{
  "path": "app.py"
}
```

Выход:

```json
{
  "ok": true,
  "content": "...",
  "chars": 1000
}
```

Ограничения:

- читать только файлы внутри workspace;
- лимит размера файла, например 200 KB;
- если файл большой, вернуть ошибку.

### 8.5. Tool: `write_file`

Вход:

```json
{
  "path": "app.py",
  "content": "..."
}
```

Выход:

```json
{
  "ok": true,
  "bytes_written": 1234
}
```

Ограничения:

- писать только внутри workspace;
- нельзя писать за пределы workspace;
- фиксировать изменение в transcript;
- перед перезаписью сохранять старое содержимое для diff.

### 8.6. Tool: `append_file`

Вход:

```json
{
  "path": "notes.txt",
  "content": "..."
}
```

Выход:

```json
{
  "ok": true,
  "bytes_appended": 123
}
```

### 8.7. Tool: `run_command`

Вход:

```json
{
  "command": "python -m pytest -q",
  "timeout_seconds": 60
}
```

Выход:

```json
{
  "ok": true,
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "duration_sec": 3.42
}
```

Команды выполнять только внутри workspace.

### 8.8. Tool: `finish`

Вход:

```json
{
  "summary": "Исправил app.py, тесты проходят.",
  "status": "done"
}
```

После `finish` скрипт запускает финальные проверки.

---

## 9. Безопасность команд

### 9.1. Разрешённые команды

Разрешить только safe-команды:

```text
python
py
pytest
pip
dir
type
Get-ChildItem
Get-Content
Select-String
powershell -NoProfile
```

### 9.2. Запрещённые команды

Запретить:

```text
del
erase
rmdir
Remove-Item
format
shutdown
restart-computer
taskkill
reg delete
curl
wget
Invoke-WebRequest
Invoke-RestMethod
ssh
scp
ftp
```

Исключение: `pip install` можно разрешить только внутри venv и только для зависимостей тестового проекта, если тест явно требует.

### 9.3. Ограничение workspace

Все команды должны запускаться с `cwd=workspace`.

Проверять, что никакой путь не выходит за workspace.

---

## 10. Встроенные агентские тесты

### 10.1. `agent_bugfix_file_edit`

Цель: проверить, может ли модель исправить файл и прогнать тесты.

Стартовый workspace:

```text
workspace/
  app.py
  tests/
    test_app.py
  requirements.txt
```

`app.py` содержит ошибки:

- неправильный SQL;
- небезопасный insert;
- не закрывается соединение;
- `true` вместо `True`;
- нет создания таблицы.

Задача модели:

```text
Исправь app.py. Не меняй tests/test_app.py. Запусти pytest. Добейся прохождения тестов.
```

Финальная проверка:

```powershell
python -m pytest -q
```

Успех:

```text
exit_code == 0
app.py изменён
tests/test_app.py не изменён
```

---

### 10.2. `agent_add_fastapi_health_endpoint`

Цель: проверить добавление endpoint в существующий проект.

Стартовый workspace:

```text
workspace/
  main.py
  tests/
    test_health.py
  requirements.txt
```

Задача:

```text
Добавь GET /health. Endpoint должен вернуть {"status": "ok"} и версию Python.
Запусти тесты и исправь ошибки.
```

Финальная проверка:

```powershell
python -m pytest -q
```

---

### 10.3. `agent_refactor_without_breaking_tests`

Цель: проверить рефакторинг.

Стартовый workspace:

```text
workspace/
  app.py
  tests/
    test_app.py
  requirements.txt
```

Задача:

```text
Раздели app.py на db.py, models.py, main.py. Сохрани публичное поведение API.
Тесты должны пройти.
```

Финальная проверка:

```powershell
python -m pytest -q
```

Успех:

```text
тесты прошли
созданы db.py, models.py, main.py
старый app.py либо сохранён как совместимый entrypoint, либо корректно заменён
```

---

### 10.4. `agent_rag_pipeline_minimal`

Цель: проверить создание простого pipeline для RAG.

Стартовый workspace:

```text
workspace/
  docs/
    doc1.txt
    doc2.md
  tests/
    test_prepare_rag.py
```

Задача:

```text
Создай prepare_rag_dataset.py. Он должен читать docs/, делать chunking и создавать rag_chunks.jsonl + manifest.json.
Запусти тесты.
```

Финальная проверка:

```powershell
python -m pytest -q
```

Успех:

```text
rag_chunks.jsonl создан
manifest.json создан
количество chunks > 0
pytest проходит
```

---

### 10.5. `agent_powershell_runner`

Цель: проверить способность создать PowerShell runner.

Стартовый workspace:

```text
workspace/
  main.py
  requirements.txt
  tests/
    test_runner_file.py
```

Задача:

```text
Создай run_fastapi.ps1 для Windows. Скрипт должен создать .venv, поставить зависимости и запустить main.py на порту 8010.
Не запускай бесконечный сервер в тесте; добавь режим -CheckOnly.
```

Финальная проверка:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_fastapi.ps1 -CheckOnly
python -m pytest -q
```

---

## 11. Transcript

Для каждого агентского запуска сохранять `transcript.jsonl`.

Каждая строка — JSON.

Пример:

```json
{
  "step": 1,
  "timestamp": "2026-05-11 10:45:12",
  "type": "model_response",
  "model": "qwen2.5-coder:3b",
  "content": "{...}",
  "tokens": 340,
  "duration_sec": 12.3
}
```

```json
{
  "step": 1,
  "timestamp": "2026-05-11 10:45:13",
  "type": "tool_result",
  "tool": "read_file",
  "ok": true,
  "result": {
    "chars": 1200
  }
}
```

---

## 12. Diff

После завершения теста сохранить:

```text
final_diff.patch
```

Diff должен показывать изменения между исходным workspace и финальным workspace.

Можно использовать:

```powershell
git diff --no-index initial workspace
```

или Python `difflib.unified_diff`.

---

## 13. Markdown-отчёт

В `model_agent_ai_report.md` для каждого результата писать:

```markdown
## AGENT_TEST_RESULT: qwen2.5-coder:3b / agent_bugfix_file_edit

| Поле | Значение |
|---|---|
| run_id | RUN-... |
| model | qwen2.5-coder:3b |
| agent_test_id | agent_bugfix_file_edit |
| prompt_id | PROMPT-... |
| config_id | CONFIG-... |
| final_status | FINISHED |
| final_check_status | PASS |
| duration_sec | 142.35 |
| steps | 8 |
| tool_calls | 14 |
| files_read | 3 |
| files_written | 1 |
| commands_run | 2 |
| max_steps_reached | false |
```

Дополнительно в отчёт включить:

```text
Final command result
Changed files
Final diff
Agent transcript
```

---

## 14. Статусы

### 14.1. `request_status`

```text
OK
HTTP_ERROR
TIMEOUT
ERROR
SKIPPED
```

### 14.2. `agent_status`

```text
FINISHED
MAX_STEPS_REACHED
INVALID_JSON
TOOL_ERROR
COMMAND_BLOCKED
MODEL_TIMEOUT
MODEL_ERROR
```

### 14.3. `final_check_status`

```text
PASS
FAIL
NOT_RUN
```

---

## 15. Ошибки JSON от модели

Если модель вернула невалидный JSON:

1. Сохранить сырой ответ.
2. Дать модели одну попытку исправить формат:

```text
Твой предыдущий ответ не был валидным JSON. Верни только один JSON-объект с tool и args.
```

3. Если снова невалидно — `agent_status=INVALID_JSON`.

Количество таких retry должно быть ограничено, например `--json-repair-attempts 1`.

---

## 16. Конфигурация генерации Ollama

Параметры по умолчанию для agent mode:

```text
num_ctx = 4096
num_predict = 1000
temperature = 0.1
timeout_seconds = 900
keep_alive = 0s
max_agent_steps = 20
```

CLI-параметры:

```text
--num-ctx
--num-predict
--temperature
--timeout-seconds
--keep-alive
--max-agent-steps
```

---

## 17. Совместимость

Скрипт должен работать на:

```text
Windows 10
PowerShell 5.1+
Python 3.10+
Ollama local API
CPU-only environment
```

Не требовать Docker.

Не требовать WSL.

Не требовать GPU.

---

## 18. Зависимости

Для самого тестера желательно использовать только:

```text
requests
```

Зависимости для тестовых workspace устанавливать внутри `.venv` workspace, если тест этого требует.

---

## 19. Приоритет реализации

### Этап 1. MVP

Реализовать:

1. CLI.
2. Список моделей из Ollama.
3. `RUN_ID`, `PROMPT_ID`, `CONFIG_ID`.
4. Workspace creation.
5. Tools:
   - list_dir
   - read_file
   - write_file
   - run_command
   - finish
6. Один тест `agent_bugfix_file_edit`.
7. Финальный `pytest`.
8. Markdown-отчёт.
9. Transcript JSONL.

### Этап 2. Дополнительные тесты

Добавить:

1. `agent_add_fastapi_health_endpoint`.
2. `agent_refactor_without_breaking_tests`.
3. `agent_rag_pipeline_minimal`.
4. `agent_powershell_runner`.

### Этап 3. Улучшения

Добавить:

1. diff.
2. JSON repair retry.
3. command whitelist.
4. skip existing.
5. aggregate raw summary.
6. запуск всех моделей и всех agent tests.

---

## 20. Критерии приёмки

Скрипт считается готовым, если:

1. Запускается командой:

```powershell
py .\model_agent_test_v11.py --agent-test agent_bugfix_file_edit --model qwen2.5-coder:3b
```

2. Создаёт workspace.
3. Модель получает задачу.
4. Модель может использовать минимум `read_file`, `write_file`, `run_command`, `finish`.
5. Выполняется не более `max_agent_steps`.
6. Итоговая проверка `pytest` запускается автоматически.
7. Создаётся `model_agent_ai_report.md`.
8. Создаётся `transcript.jsonl`.
9. Создаётся `final_diff.patch`.
10. В отчёте есть все факты по запуску.
11. Скрипт не выставляет баллы и рейтинги.
12. Команды не могут выйти за пределы workspace.
13. Опасные команды блокируются.
14. Повторный запуск не перезаписывает старые результаты.
15. Можно загрузить Markdown-отчёт в любой ИИ и попросить сделать анализ.

---

## 21. Пример системного prompt для агента

```text
Ты локальный coding agent. Ты работаешь только через инструменты.

Правила:
1. Отвечай только валидным JSON-объектом.
2. Не пиши Markdown.
3. Не пиши объяснения вне JSON.
4. Используй только один tool за шаг.
5. Не выдумывай содержимое файлов: сначала прочитай файл через read_file.
6. Не меняй тесты, если задача не разрешает.
7. После изменений запускай проверку через run_command.
8. Когда задача выполнена, вызови finish.

Доступные tools:
- list_dir
- read_file
- write_file
- append_file
- run_command
- finish
```

---

## 22. Пример JSON-ответа модели

```json
{
  "thought_summary": "Нужно открыть app.py и tests/test_app.py, чтобы понять ошибку.",
  "tool": "read_file",
  "args": {
    "path": "app.py"
  }
}
```

---

## 23. Риски

1. Маленькие модели могут не соблюдать JSON.
2. Модели могут писать Markdown вместо JSON.
3. Модели могут пытаться выполнить запрещённые команды.
4. Модели могут редактировать тесты вместо исходного кода.
5. Модели могут зациклиться.
6. Некоторые модели будут слишком медленные на CPU.
7. `num_ctx=4096` может быть мало для больших workspace.
8. `num_predict=1000` может обрезать сложные ответы.
9. `py_compile=PASS` не гарантирует рабочую бизнес-логику.
10. Командный sandbox должен быть строгим.

---

## 24. Рекомендованные первые модели для проверки

Сначала тестировать:

```text
qwen2.5-coder:1.5b
qwen2.5-coder:3b
qwen2.5-coder:7b
```

Дополнительно:

```text
llama3.1:8b
deepseek-coder-v2:lite
phi4:latest
gemma3:4b
```

Не использовать как основные, если подтверждается плохое поведение:

```text
starcoder2:3b
stable-code:3b
deepseek-r1:1.5b
bitnet_b1_58-3B
```

---

## 25. Итог

Новый `model_agent_test_v11.py` должен стать не заменой `model_performance_test_v10.py`, а отдельным инструментом.

`model_performance_test_v10.py` отвечает на вопрос:

```text
Как модель отвечает на coding prompt одним сообщением?
```

`model_agent_test_v11.py` должен отвечать на вопрос:

```text
Может ли модель реально работать как coding agent: читать файлы, менять проект, запускать тесты и исправлять ошибки?
```
