# Ollama CPU Coding Benchmark

Проект для локального тестирования Ollama-моделей на CPU в задачах кодинга.

Главная цель: собрать честные данные по моделям, чтобы потом загрузить Markdown-отчёт в ChatGPT/Claude/Kimi/Cursor/Codex и выбрать лучшие модели для локального coding agent.

## Что делает проект

- Берёт список установленных моделей из Ollama (`/api/tags`).
- Запускает набор coding-тестов по каждой модели.
- Сохраняет `RUN_ID`, `PROMPT_ID`, `CONFIG_ID`, время, токены, ошибки и полный ответ модели.
- Не ставит автоматические оценки качества и не строит фейковый рейтинг.
- Пишет AI-readable отчёт в Markdown.

## Структура

```text
ollama-cpu-coding-benchmark/
├─ README.md
├─ requirements.txt
├─ .gitignore
├─ tools/
│  ├─ model_performance_test.py
│  ├─ run_benchmark_with_download.ps1
│  └─ download_models.ps1
├─ docs/
│  └─ ai_analysis_prompt.md
└─ examples/
   └─ model_benchmark_ai_report_sample.md
```

## Требования

- Windows 10/11
- Python 3.10+
- Ollama
- PowerShell 7 желательно, но можно и Windows PowerShell
- Установленные модели Ollama

Проверка:

```powershell
ollama list
py --version
```

## Установка Python-зависимостей

Скрипт умеет сам установить `requests`, если модуля нет. Но можно поставить вручную:

```powershell
cd C:\Work\Prj_1_AI_Test\tools
py -m pip install -r ..\requirements.txt
```

## Быстрый запуск всех установленных моделей и всех тестов

```powershell
cd C:\Work\Prj_1_AI_Test\tools
py .\model_performance_test.py --no-pull --full
```

Что значит:

```text
--no-pull  = не скачивать модели внутри Python-скрипта
--full     = запустить все тесты
модели    = взять все установленные модели из Ollama
```

## Запуск через PowerShell-wrapper

Wrapper удобен, если нужно сначала скачать модели красивым штатным прогрессом `ollama pull`, а потом запустить benchmark.

```powershell
cd C:\Work\Prj_1_AI_Test\tools
Unblock-File .\run_benchmark_with_download.ps1
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\run_benchmark_with_download.ps1 -NoDownload -Full
```

Если нужно сначала скачать модели, убери `-NoDownload`:

```powershell
.\run_benchmark_with_download.ps1 -PullSet cpu -Full
```

## Полезные команды

Показать список встроенных тестов и `PROMPT_ID`:

```powershell
py .\model_performance_test.py --list-tests
```

Запустить одну модель:

```powershell
py .\model_performance_test.py --no-pull --model qwen2.5-coder:3b --full
```

Запустить один test case:

```powershell
py .\model_performance_test.py --no-pull --test-case rag_local_docs_fastapi_sqlite_fts
```

Запустить разовый prompt из файла:

```powershell
py .\model_performance_test.py --no-pull --prompt-file .\my_one_time_test.txt --model qwen2.5-coder:3b
```

Принудительно повторить уже выполненный тест:

```powershell
py .\model_performance_test.py --no-pull --full --rerun-existing
```

## Выходные файлы

После запуска рядом со скриптом появятся:

```text
model_performance_test.log
model_benchmark_ai_report.md
```

`model_benchmark_ai_report.md` — главный файл. Его можно загрузить в любой ИИ и попросить оценить модели.

## Что такое RUN_ID, PROMPT_ID, CONFIG_ID

- `RUN_ID` — уникальный идентификатор запуска.
- `PROMPT_ID` — стабильный идентификатор prompt, SHA-256 от нормализованного текста.
- `CONFIG_ID` — идентификатор настроек теста: `num_ctx`, `num_predict`, `temperature`, `timeout`.

Это нужно, чтобы не гонять один и тот же prompt повторно на одной модели с теми же настройками.

## Почему в отчёте нет автоматической оценки

Автоматическая оценка по ключевым словам слишком доверчивая. Она может поставить высокий балл ответу, где модель просто пересказала задачу или написала синтаксически сломанный код.

Поэтому скрипт сохраняет только факты:

```text
request_status
response_status
duration_seconds
output_tokens
tokens_per_second
response_chars
hit_token_limit
python_compile_status
error_text
full model response
```

Оценку делает человек или отдельный ИИ-анализатор.

## Текущие категории тестов

- FastAPI + SQLite + Node.js health endpoint
- Исправление багов Python
- SQLite analytics queries
- PowerShell runner for FastAPI project
- 1C/OData client
- RAG system over local documents
- Web scraping pipeline
- BM25/TF-IDF/hybrid search
- Information extraction pipeline
- Document processing for RAG dataset

## Рекомендация по запуску на CPU

Полный запуск может занять много времени:

```text
количество моделей × количество тестов
```

Например:

```text
14 моделей × 10 тестов = 140 запусков модели
```

Такой тест лучше оставлять на ночь.

## Как анализировать отчёт

После теста открой или загрузи файл:

```text
model_benchmark_ai_report.md
```

И используй prompt из `docs/ai_analysis_prompt.md`.
