#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
model_performance_test_v10.py

Ollama CPU coding benchmark collector.

Главная идея v10:
- Скрипт НЕ оценивает модели баллами.
- Скрипт собирает только факты: время, токены, ошибки, полный ответ модели, PROMPT_ID, CONFIG_ID.
- Итоговый Markdown-файл удобно загружать в любой ИИ для независимого анализа.

Выходные файлы:
- model_performance_test.log        технический лог
- model_benchmark_ai_report.md      AI-readable отчёт

Примеры:
    py .\model_performance_test_v10.py
    py .\model_performance_test_v10.py --full
    py .\model_performance_test_v10.py --model qwen2.5-coder:3b
    py .\model_performance_test_v10.py --prompt-file .\my_test.txt --model qwen2.5-coder:3b
    py .\model_performance_test_v10.py --list-tests
    py .\model_performance_test_v10.py --rerun-existing
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCRIPT_VERSION = "v10.0"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
LOG_FILENAME = "model_performance_test.log"
REPORT_FILENAME = "model_benchmark_ai_report.md"

DEFAULT_NUM_CTX = 2048
DEFAULT_NUM_PREDICT = 1200
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_KEEP_ALIVE = "0s"

MODEL_SETS: Dict[str, List[str]] = {
    "quick": [
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:3b",
        "codegemma:2b",
        "deepseek-coder:1.3b",
    ],
    "cpu": [
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:3b",
        "codegemma:2b",
        "deepseek-coder:1.3b",
        "starcoder2:3b",
        "granite-code:3b",
        "stable-code:3b",
        "yi-coder:1.5b",
    ],
    "heavy": [
        "qwen2.5-coder:7b",
        "deepseek-coder:6.7b",
        "mistral:7b-instruct-v0.3",
        "codellama:7b-instruct",
    ],
}
MODEL_SETS["all"] = list(dict.fromkeys(MODEL_SETS["cpu"] + MODEL_SETS["heavy"] + [
    "llama3.2:3b",
    "phi3:mini",
]))


# ----------------------------- dependency bootstrap -----------------------------

def ensure_requests() -> None:
    """Install requests if it is missing, before importing it."""
    if importlib.util.find_spec("requests") is not None:
        return

    print("[SETUP] Python module 'requests' не найден. Пробую установить автоматически...")
    try:
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False)
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=False)
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
    except Exception as exc:
        print(f"[ERROR] Не удалось установить requests: {exc}")
        print("Выполни вручную:")
        print(f"  {sys.executable} -m pip install requests")
        raise


ensure_requests()
import requests  # noqa: E402  # pylint: disable=wrong-import-position


# ----------------------------- data models -----------------------------

@dataclass(frozen=True)
class TestCase:
    test_case_id: str
    title: str
    category: str
    prompt: str

    @property
    def prompt_id(self) -> str:
        return compute_prompt_id(self.prompt)


@dataclass
class PullRecord:
    model: str
    status: str
    attempts: int
    duration_seconds: float
    error: str = ""


@dataclass
class StaticFacts:
    code_block_count: int = 0
    extracted_python_chars: int = 0
    extracted_python_lines: int = 0
    python_compile_status: str = "NOT_CHECKED"  # PASS / FAIL / NO_CODE / NOT_CHECKED
    python_compile_error: str = ""


@dataclass
class ModelResult:
    run_id: str
    test_case_id: str
    prompt_id: str
    config_id: str
    model_name: str
    request_status: str  # OK / HTTP_ERROR / ERROR / TIMEOUT / SKIPPED
    response_status: str  # HAS_TEXT / EMPTY / TRUNCATED / ERROR / SKIPPED
    http_status_code: Optional[int] = None
    duration_seconds: Optional[float] = None
    duration_hms: str = ""
    output_tokens: Optional[int] = None
    tokens_per_second: Optional[float] = None
    response_chars: int = 0
    hit_token_limit: bool = False
    error_text: str = ""
    response_text: str = ""
    raw_ollama: Dict[str, Any] = field(default_factory=dict)
    static_facts: StaticFacts = field(default_factory=StaticFacts)


# ----------------------------- built-in test cases -----------------------------

BUILTIN_TEST_CASES: List[TestCase] = [
    TestCase(
        test_case_id="fastapi_sqlite_node_health",
        title="FastAPI + SQLite + Node.js health endpoint",
        category="backend",
        prompt=textwrap.dedent("""
            Создай один полный файл main.py.

            Контекст:
            Я тестирую локальную CPU-модель для реальной работы coding agent.
            Меня интересует качество кода для Python, FastAPI, SQLite и проверки Node.js.

            Требования:
            1. Используй FastAPI.
            2. Используй SQLite базу cars.db.
            3. Создай таблицу cars:
               - id INTEGER PRIMARY KEY AUTOINCREMENT
               - plate TEXT UNIQUE NOT NULL
               - owner TEXT NOT NULL
               - created_at TEXT NOT NULL
            4. Сделай POST /cars для добавления автомобиля.
            5. Сделай GET /cars для списка автомобилей.
            6. Сделай GET /cars/{plate} для поиска автомобиля по госномеру.
            7. Сделай GET /health.
            8. Endpoint /health должен проверить:
               - SQLite доступен
               - версия Python
               - установлен ли Node.js через команду node --version
            9. Если Node.js не установлен, сервер не должен падать. Верни в health статус node_installed=false.
            10. Используй Pydantic-модель для входных данных.
            11. Добавь обработку ошибок FastAPI через HTTPException.
            12. Добавь блок запуска:
                if __name__ == "__main__":
                    import uvicorn
                    uvicorn.run(app, host="0.0.0.0", port=8010)

            Важно:
            - Верни только полный код файла main.py.
            - Не пиши объяснения до или после кода.
            - Код должен быть пригоден для запуска на Windows.
        """).strip(),
    ),
    TestCase(
        test_case_id="python_bugfix_full_file",
        title="Python bugfix: return full corrected file",
        category="bugfix",
        prompt=textwrap.dedent("""
            Исправь ошибки в коде и верни только полный исправленный файл app.py.
            Не пиши объяснения до или после кода.

            Код:

            from fastapi import FastAPI
            import sqlite3

            app = FastAPI()

            def get_conn():
                conn = sqlite3.connect("data.db")
                return conn.cursor()

            @app.get("/items")
            def items():
                cur = get_conn()
                rows = cur.execute("select id name from items").fetchall()
                return [{"id": r[0], "name": r[1]} for r in rows]

            @app.post("/items")
            def add_item(name: str):
                cur = get_conn()
                cur.execute(f"insert into items(name) values('{name}')")
                return {"ok": true}

            Требования к исправлению:
            1. Создай таблицу items, если её нет.
            2. Исправь SQL SELECT.
            3. Закрывай SQLite connection.
            4. Не используй f-string для SQL insert.
            5. Исправь true на корректное Python-значение.
            6. Добавь запуск uvicorn на порту 8010.
        """).strip(),
    ),
    TestCase(
        test_case_id="sqlite_analytics_queries",
        title="SQLite schema and analytics queries",
        category="sql",
        prompt=textwrap.dedent("""
            Верни только SQL-код без объяснений.

            Создай SQLite-схему для автомойки:
            - clients: id, name, phone, created_at
            - cars: id, client_id, plate, brand, created_at
            - visits: id, car_id, service_name, amount, visited_at

            Требования:
            1. Добавь PRIMARY KEY и FOREIGN KEY.
            2. Добавь UNIQUE на cars.plate.
            3. Напиши 5 SELECT-запросов:
               - список визитов за период
               - топ клиентов по сумме
               - история автомобиля по госномеру
               - количество визитов по дням
               - средний чек по услуге
            4. Код должен быть совместим с SQLite.
        """).strip(),
    ),
    TestCase(
        test_case_id="powershell_fastapi_runner",
        title="PowerShell script for FastAPI project on Windows",
        category="powershell",
        prompt=textwrap.dedent("""
            Создай полный PowerShell-скрипт run_fastapi.ps1.
            Верни только код скрипта, без объяснений.

            Требования:
            1. Проверить наличие Python через py или python.
            2. Создать .venv, если её нет.
            3. Активировать .venv.
            4. Установить fastapi, uvicorn, pydantic.
            5. Запустить main.py на порту 8010.
            6. Если main.py отсутствует, вывести понятную ошибку.
            7. Логировать шаги в консоль.
            8. Скрипт должен работать на Windows PowerShell 5.1+ и PowerShell 7.
        """).strip(),
    ),
    TestCase(
        test_case_id="onedata_1c_client",
        title="Python OData 1C client",
        category="integration",
        prompt=textwrap.dedent("""
            Создай один полный Python-файл odata_1c_client.py.
            Верни только код файла, без объяснений.

            Контекст:
            Нужен клиент для OData 1C.

            Требования:
            1. Класс OData1CClient.
            2. Конструктор: base_url, username, password, timeout=30.
            3. Используй requests.Session.
            4. Метод get_counterparties(limit=100) делает GET к справочнику Контрагенты.
            5. Метод get_json(path, params=None) для универсального GET.
            6. Обработка HTTP ошибок через raise_for_status.
            7. Обработка сетевых ошибок requests.RequestException.
            8. Верни понятные исключения с текстом ошибки.
            9. Добавь пример использования под if __name__ == "__main__".
            10. Код должен быть пригоден для Windows.
        """).strip(),
    ),

    TestCase(
        test_case_id="rag_local_docs_fastapi_sqlite_fts",
        title="Local RAG system: FastAPI + SQLite FTS5 + file ingestion",
        category="rag",
        prompt=textwrap.dedent("""
            Создай один полный файл rag_app.py.
            Верни только код файла, без объяснений.

            Контекст:
            Я тестирую локальную CPU-модель для задач RAG и поиска по документам.
            Нужна простая RAG-система без платных API и без внешней векторной базы.

            Требования:
            1. Используй FastAPI.
            2. Используй SQLite базу rag.db.
            3. Используй SQLite FTS5 для полнотекстового поиска, если FTS5 доступен.
            4. Если FTS5 недоступен, сделай fallback на LIKE-поиск.
            5. Поддержи загрузку локальных файлов .txt и .md из папки data/.
            6. Сделай chunking документов:
               - chunk_size примерно 800 символов
               - overlap примерно 120 символов
            7. Создай таблицы documents и chunks.
            8. Endpoint POST /ingest должен переиндексировать файлы из data/.
            9. Endpoint GET /search?q=... должен вернуть top_k найденных chunk-ов.
            10. Endpoint POST /ask должен:
                - принять JSON {"question": "...", "top_k": 5}
                - найти релевантные chunks
                - вернуть answer_prompt, context_chunks и sources
                - не вызывать внешнюю LLM, только подготовить prompt для RAG.
            11. Endpoint GET /health должен проверить SQLite и доступность папки data/.
            12. Используй Pydantic-модели для входных данных.
            13. Добавь обработку ошибок через HTTPException.
            14. Добавь запуск uvicorn на host 0.0.0.0 port 8010.
            15. Код должен быть пригоден для Windows.
        """).strip(),
    ),
    TestCase(
        test_case_id="web_scraping_bs4_sqlite_pipeline",
        title="Web scraping pipeline: requests + BeautifulSoup + SQLite",
        category="web_scraping",
        prompt=textwrap.dedent("""
            Создай один полный файл web_scraper.py.
            Верни только код файла, без объяснений.

            Контекст:
            Я тестирую локальную CPU-модель для задач web scraping и извлечения информации.

            Требования:
            1. Используй requests и BeautifulSoup из bs4.
            2. Не используй Selenium и браузерную автоматизацию.
            3. Создай класс WebScraper.
            4. Конструктор принимает base_url=None, timeout=20, delay_seconds=1.0.
            5. Используй requests.Session и нормальный User-Agent.
            6. Метод fetch(url) делает GET с timeout, обработкой HTTP ошибок и сетевых ошибок.
            7. Метод parse(html, url) извлекает:
               - title
               - h1
               - meta description
               - все ссылки href с абсолютными URL
               - основной текст из p/li/article/main
            8. Метод save_page(data) сохраняет результат в SQLite scrape.db.
            9. Таблицы: pages и links.
            10. Метод scrape_many(urls) обрабатывает список URL, уважает delay_seconds, не падает при ошибке одного URL.
            11. CLI-блок if __name__ == "__main__" должен принять URL из аргументов командной строки.
            12. Добавь экспорт результатов в JSONL-файл scrape_results.jsonl.
            13. Код должен быть пригоден для Windows.
        """).strip(),
    ),
    TestCase(
        test_case_id="search_methods_bm25_tfidf_hybrid",
        title="Search methods: BM25 + TF-IDF-like scoring + hybrid ranking",
        category="search",
        prompt=textwrap.dedent("""
            Создай один полный файл search_engine.py.
            Верни только код файла, без объяснений.

            Контекст:
            Я тестирую локальную CPU-модель для популярных методов поиска и обработки информации.
            Нужен маленький локальный поисковый движок без внешних сервисов.

            Требования:
            1. Используй только стандартную библиотеку Python.
            2. Реализуй нормализацию текста:
               - lowercase
               - удаление лишней пунктуации
               - простая токенизация
               - stop words для русского и английского минимум по 10 слов
            3. Реализуй индекс документов в памяти.
            4. Реализуй BM25 scoring.
            5. Реализуй простой TF-IDF-like scoring.
            6. Реализуй hybrid_search(query, top_k=5), который смешивает BM25 и TF-IDF.
            7. Добавь функцию make_snippet(text, query), которая показывает фрагмент вокруг найденного слова.
            8. Добавь дедупликацию документов по sha256 текста.
            9. Добавь класс SearchEngine с методами:
               - add_document(doc_id, text, metadata=None)
               - search(query, top_k=5)
               - explain(query, doc_id)
            10. В if __name__ == "__main__" добавь демонстрацию на 5 документах.
            11. Код должен быть пригоден для Windows и Python 3.10+.
        """).strip(),
    ),
    TestCase(
        test_case_id="information_extraction_pipeline_regex_json_csv",
        title="Information extraction pipeline: regex + normalization + JSON/CSV",
        category="information_processing",
        prompt=textwrap.dedent("""
            Создай один полный файл info_extractor.py.
            Верни только код файла, без объяснений.

            Контекст:
            Я тестирую локальную CPU-модель для обработки информации из документов и текстов.

            Требования:
            1. Используй только стандартную библиотеку Python.
            2. Скрипт должен читать все .txt файлы из папки input_texts/.
            3. Из каждого текста извлечь:
               - email
               - телефоны
               - суммы денег
               - даты в форматах dd.mm.yyyy, yyyy-mm-dd
               - ИИН/БИН Казахстана как 12 цифр
               - госномера авто в простом формате Казахстана, например 123ABC02 или 777AAA05
            4. Сделай нормализацию телефонов и дат.
            5. Сохрани результат в SQLite базу extracted_info.db.
            6. Экспортируй результат в extracted_info.json и extracted_info.csv.
            7. Добавь dataclass ExtractedRecord.
            8. Добавь функции:
               - extract_from_text(text, source_name)
               - normalize_phone(value)
               - normalize_date(value)
               - save_to_sqlite(records)
               - export_json(records)
               - export_csv(records)
            9. Скрипт не должен падать, если папки input_texts/ нет: он должен создать её и вывести понятное сообщение.
            10. Код должен быть пригоден для Windows.
        """).strip(),
    ),
    TestCase(
        test_case_id="document_processing_rag_preparation_pipeline",
        title="Document processing for RAG: chunking + metadata + manifest",
        category="document_processing",
        prompt=textwrap.dedent("""
            Создай один полный файл prepare_rag_dataset.py.
            Верни только код файла, без объяснений.

            Контекст:
            Мне нужен подготовительный pipeline для RAG: обработать локальные документы, нарезать на chunks и сохранить dataset для дальнейшего анализа любым ИИ.

            Требования:
            1. Используй только стандартную библиотеку Python.
            2. Читай документы .txt и .md из папки docs/.
            3. Очищай текст:
               - убирай повторяющиеся пробелы
               - нормализуй переносы строк
               - удаляй слишком короткие строки навигации
            4. Делай chunking:
               - chunk_size_chars=1200
               - overlap_chars=200
               - не разрывай текст внутри предложения, если это возможно.
            5. Для каждого chunk сохраняй metadata:
               - source_file
               - chunk_index
               - char_start
               - char_end
               - sha256
               - created_at
            6. Сохрани результат в rag_chunks.jsonl.
            7. Сохрани manifest.json со статистикой:
               - количество файлов
               - количество chunks
               - средняя длина chunk
               - список файлов
            8. Добавь защиту от дублей chunks по sha256.
            9. Добавь CLI-параметры --docs-dir, --out-jsonl, --manifest.
            10. Код должен быть пригоден для Windows.
        """).strip(),
    ),
]


# ----------------------------- utility functions -----------------------------

def now_str() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_id() -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    return f"RUN-{stamp}-{suffix}"


def normalize_prompt_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.strip().split("\n")]
    # Keep meaningful line breaks, remove excessive blank lines.
    normalized_lines: List[str] = []
    blank_seen = False
    for line in lines:
        if not line.strip():
            if not blank_seen:
                normalized_lines.append("")
            blank_seen = True
        else:
            normalized_lines.append(line)
            blank_seen = False
    return "\n".join(normalized_lines).strip()


def compute_prompt_id(prompt: str) -> str:
    digest = hashlib.sha256(normalize_prompt_text(prompt).encode("utf-8")).hexdigest()
    return "PROMPT-" + digest[:16].upper()


def compute_config_id(config: Dict[str, Any]) -> str:
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return "CONFIG-" + digest[:16].upper()


def seconds_to_hms(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    return str(_dt.timedelta(seconds=round(seconds)))


def short_error(text: str, max_len: int = 160) -> str:
    text = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("|", "\\|")
    text = text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    return text


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    out = []
    out.append("| " + " | ".join(md_escape(h) for h in headers) + " |")
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(md_escape(v) for v in row) + " |")
    return "\n".join(out)


def fence(text: str, lang: str = "text") -> str:
    text = "" if text is None else str(text)
    max_ticks = 3
    for match in re.finditer(r"`+", text):
        max_ticks = max(max_ticks, len(match.group(0)) + 1)
    ticks = "`" * max_ticks
    return f"{ticks}{lang}\n{text}\n{ticks}"


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text_append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(text)


def log_line(log_path: Path, run: str, level: str, message: str) -> None:
    line = f"[{now_str()}] [{level}] [{run}] {message}"
    print(line)
    write_text_append(log_path, line + "\n")


def command_output(command: Sequence[str], timeout: int = 10) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        output = (completed.stdout or completed.stderr or "").strip()
        return output if output else "NOT AVAILABLE"
    except Exception:
        return "NOT AVAILABLE"


def ollama_executable() -> str:
    return shutil.which("ollama") or "ollama"


# ----------------------------- report parsing / skip logic -----------------------------

def parse_existing_results(report_path: Path) -> set[Tuple[str, str, str]]:
    """Return set of (model_name, prompt_id, config_id) already present in report."""
    existing: set[Tuple[str, str, str]] = set()
    if not report_path.exists():
        return existing

    pattern = re.compile(r"<!--\s*BENCH_RESULT\s+(\{.*?\})\s*-->", re.DOTALL)
    text = read_text_file(report_path)
    for match in pattern.finditer(text):
        raw = match.group(1)
        try:
            data = json.loads(raw)
        except Exception:
            continue
        model_name = data.get("model_name")
        prompt_id = data.get("prompt_id")
        config_id = data.get("config_id")
        if model_name and prompt_id and config_id:
            existing.add((str(model_name), str(prompt_id), str(config_id)))
    return existing


# ----------------------------- static facts -----------------------------

def extract_python_code(response_text: str) -> Tuple[str, int]:
    """Extract Python-looking code from response text without executing it."""
    if not response_text.strip():
        return "", 0

    code_blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", response_text, flags=re.IGNORECASE | re.DOTALL)
    if code_blocks:
        # Prefer the largest code block.
        code = max(code_blocks, key=len).strip()
        return code, len(code_blocks)

    # If model returned raw code without fences, try to detect Python by keywords.
    python_markers = ["from fastapi", "import ", "def ", "class ", "@app.", "if __name__"]
    lower = response_text.lower()
    if any(marker in lower for marker in python_markers):
        return response_text.strip(), 0

    return "", 0


def compile_python_code(code: str) -> Tuple[str, str]:
    if not code.strip():
        return "NO_CODE", ""
    with tempfile.TemporaryDirectory(prefix="ollama_bench_compile_") as tmp:
        path = Path(tmp) / "candidate.py"
        path.write_text(code, encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "FAIL", "py_compile timeout"
        except Exception as exc:
            return "FAIL", str(exc)

        if completed.returncode == 0:
            return "PASS", ""
        return "FAIL", (completed.stderr or completed.stdout or "py_compile failed").strip()


def collect_static_facts(response_text: str, enable_syntax_check: bool) -> StaticFacts:
    code, block_count = extract_python_code(response_text)
    facts = StaticFacts(
        code_block_count=block_count,
        extracted_python_chars=len(code),
        extracted_python_lines=len(code.splitlines()) if code else 0,
        python_compile_status="NOT_CHECKED",
        python_compile_error="",
    )
    if enable_syntax_check:
        status, err = compile_python_code(code)
        facts.python_compile_status = status
        facts.python_compile_error = err
    return facts


# ----------------------------- Ollama operations -----------------------------

def get_ollama_models(ollama_url: str, timeout: int = 10) -> List[str]:
    response = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    models = data.get("models", [])
    names = [m.get("name") for m in models if m.get("name")]
    return sorted(names)


def pull_model(model: str, max_attempts: int, log_path: Path, run: str) -> PullRecord:
    start = time.perf_counter()
    exe = ollama_executable()
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        log_line(log_path, run, "INFO", f"PULL START | model={model} | attempt={attempt}/{max_attempts}")
        print(f"\nСкачивание/проверка модели: {model} | попытка {attempt} из {max_attempts}")
        print("Сырой прогресс скрыт внутри Python. Для красивой загрузки используй PowerShell-wrapper.")
        try:
            completed = subprocess.run(
                [exe, "pull", model],
                capture_output=True,
                text=True,
                timeout=None,
                check=False,
            )
            if completed.returncode == 0:
                duration = time.perf_counter() - start
                log_line(log_path, run, "OK", f"PULL OK | model={model} | attempt={attempt}/{max_attempts} | seconds={duration:.2f}")
                return PullRecord(model=model, status="OK", attempts=attempt, duration_seconds=duration)

            last_error = (completed.stderr or completed.stdout or f"ollama pull exited with {completed.returncode}").strip()
            log_line(log_path, run, "WARN", f"PULL ERROR | model={model} | attempt={attempt}/{max_attempts} | error={short_error(last_error)}")

            # Try removing a partially broken model reference when digest mismatch occurs.
            if "digest mismatch" in last_error.lower() or "downloaded again" in last_error.lower():
                subprocess.run([exe, "rm", model], capture_output=True, text=True, check=False)
                time.sleep(3)
        except Exception as exc:
            last_error = str(exc)
            log_line(log_path, run, "WARN", f"PULL EXCEPTION | model={model} | attempt={attempt}/{max_attempts} | error={short_error(last_error)}")

        if attempt < max_attempts:
            time.sleep(5)

    duration = time.perf_counter() - start
    log_line(log_path, run, "ERROR", f"PULL FAILED | model={model} | attempts={max_attempts} | error={short_error(last_error)}")
    return PullRecord(model=model, status="ERROR", attempts=max_attempts, duration_seconds=duration, error=last_error)


def run_ollama_generate(
    *,
    run: str,
    test_case: TestCase,
    model: str,
    config_id: str,
    config: Dict[str, Any],
    ollama_url: str,
    timeout_seconds: int,
    syntax_check: bool,
    log_path: Path,
) -> ModelResult:
    prompt_id = test_case.prompt_id
    start = time.perf_counter()
    log_line(
        log_path,
        run,
        "INFO",
        f"TEST START | model={model} | test={test_case.test_case_id} | prompt_id={prompt_id} | config_id={config_id}",
    )

    payload = {
        "model": model,
        "prompt": test_case.prompt,
        "stream": False,
        "keep_alive": config.get("keep_alive", DEFAULT_KEEP_ALIVE),
        "options": {
            "num_ctx": config["num_ctx"],
            "num_predict": config["num_predict"],
            "temperature": config["temperature"],
        },
    }

    try:
        response = requests.post(
            f"{ollama_url.rstrip('/')}/api/generate",
            json=payload,
            timeout=timeout_seconds,
        )
        duration = time.perf_counter() - start
    except requests.Timeout as exc:
        duration = time.perf_counter() - start
        error_text = str(exc)
        result = ModelResult(
            run_id=run,
            test_case_id=test_case.test_case_id,
            prompt_id=prompt_id,
            config_id=config_id,
            model_name=model,
            request_status="TIMEOUT",
            response_status="ERROR",
            duration_seconds=duration,
            duration_hms=seconds_to_hms(duration),
            error_text=error_text,
        )
        log_line(log_path, run, "ERROR", f"TEST TIMEOUT | model={model} | prompt_id={prompt_id} | seconds={duration:.2f}")
        return result
    except Exception as exc:  # requests.RequestException and others
        duration = time.perf_counter() - start
        error_text = str(exc)
        result = ModelResult(
            run_id=run,
            test_case_id=test_case.test_case_id,
            prompt_id=prompt_id,
            config_id=config_id,
            model_name=model,
            request_status="ERROR",
            response_status="ERROR",
            duration_seconds=duration,
            duration_hms=seconds_to_hms(duration),
            error_text=error_text,
        )
        log_line(log_path, run, "ERROR", f"TEST ERROR | model={model} | prompt_id={prompt_id} | error={short_error(error_text)}")
        return result

    http_status = response.status_code
    if http_status != 200:
        error_text = response.text.strip()
        result = ModelResult(
            run_id=run,
            test_case_id=test_case.test_case_id,
            prompt_id=prompt_id,
            config_id=config_id,
            model_name=model,
            request_status="HTTP_ERROR",
            response_status="ERROR",
            http_status_code=http_status,
            duration_seconds=duration,
            duration_hms=seconds_to_hms(duration),
            error_text=error_text,
        )
        log_line(log_path, run, "ERROR", f"TEST HTTP_ERROR | model={model} | prompt_id={prompt_id} | http={http_status} | error={short_error(error_text)}")
        return result

    try:
        data = response.json()
    except Exception as exc:
        error_text = f"Invalid JSON from Ollama: {exc}; raw={response.text[:500]}"
        result = ModelResult(
            run_id=run,
            test_case_id=test_case.test_case_id,
            prompt_id=prompt_id,
            config_id=config_id,
            model_name=model,
            request_status="ERROR",
            response_status="ERROR",
            http_status_code=http_status,
            duration_seconds=duration,
            duration_hms=seconds_to_hms(duration),
            error_text=error_text,
        )
        log_line(log_path, run, "ERROR", f"TEST JSON_ERROR | model={model} | prompt_id={prompt_id} | error={short_error(error_text)}")
        return result

    response_text = data.get("response") or ""
    output_tokens = data.get("eval_count")
    eval_duration_ns = data.get("eval_duration")
    tokens_per_second: Optional[float] = None
    if isinstance(output_tokens, (int, float)) and isinstance(eval_duration_ns, (int, float)) and eval_duration_ns > 0:
        tokens_per_second = float(output_tokens) / (float(eval_duration_ns) / 1_000_000_000.0)

    hit_token_limit = False
    if isinstance(output_tokens, int):
        hit_token_limit = output_tokens >= int(config["num_predict"])

    stripped = response_text.strip()
    if not stripped:
        response_status = "EMPTY"
    elif hit_token_limit:
        response_status = "TRUNCATED"
    else:
        response_status = "HAS_TEXT"

    facts = collect_static_facts(response_text, enable_syntax_check=syntax_check)

    result = ModelResult(
        run_id=run,
        test_case_id=test_case.test_case_id,
        prompt_id=prompt_id,
        config_id=config_id,
        model_name=model,
        request_status="OK",
        response_status=response_status,
        http_status_code=http_status,
        duration_seconds=duration,
        duration_hms=seconds_to_hms(duration),
        output_tokens=int(output_tokens) if isinstance(output_tokens, int) else None,
        tokens_per_second=round(tokens_per_second, 2) if tokens_per_second is not None else None,
        response_chars=len(response_text),
        hit_token_limit=hit_token_limit,
        error_text="" if stripped else "Empty response text.",
        response_text=response_text,
        raw_ollama=data,
        static_facts=facts,
    )

    log_line(
        log_path,
        run,
        "OK",
        (
            f"TEST END | model={model} | test={test_case.test_case_id} | prompt_id={prompt_id} | "
            f"config_id={config_id} | request_status={result.request_status} | response_status={result.response_status} | "
            f"seconds={duration:.2f} | tokens={result.output_tokens} | chars={result.response_chars} | "
            f"hit_token_limit={result.hit_token_limit} | py_compile={facts.python_compile_status}"
        ),
    )
    return result


# ----------------------------- report writer -----------------------------

def ensure_report_header(report_path: Path) -> None:
    if report_path.exists() and report_path.stat().st_size > 0:
        return

    header = textwrap.dedent(f"""
        # Ollama CPU Coding Benchmark Report

        Этот файл предназначен для анализа любым ИИ: ChatGPT, Claude, Kimi, Cursor, Codex и другими.

        ## Цель

        Найти лучшую локальную CPU-модель Ollama для кодинга:
        - Python
        - FastAPI
        - SQLite
        - Node.js health checks
        - PowerShell/Windows
        - 1C/OData integration
        - RAG systems
        - Web scraping
        - Search / BM25 / TF-IDF
        - Information extraction and document processing

        ## Как читать результаты

        Каждый запуск имеет уникальный `RUN_ID`.
        Каждый prompt имеет стабильный `PROMPT_ID`, рассчитанный как SHA-256 от нормализованного текста prompt.
        Каждая конфигурация генерации имеет `CONFIG_ID`, рассчитанный по настройкам `num_ctx`, `num_predict`, `temperature`, `timeout_seconds`, `keep_alive` и `ollama_url`.

        ## Важно

        Начиная с версии v8, этот отчёт НЕ содержит автоматических оценок качества, рейтингов и баллов.
        Скрипт сохраняет только факты:
        - статус HTTP-запроса к Ollama
        - статус ответа модели
        - время генерации
        - количество токенов
        - скорость токенов
        - размер ответа
        - был ли достигнут лимит `num_predict`
        - сырой ответ модели
        - технические факты вроде результата `py_compile`, если включена синтаксическая проверка

        Оценку качества должен делать человек или отдельный ИИ-анализатор по полным ответам моделей.

        ---
    """).strip() + "\n\n"
    report_path.write_text(header, encoding="utf-8")


def result_to_bench_comment(result: ModelResult) -> str:
    data = {
        "run_id": result.run_id,
        "model_name": result.model_name,
        "test_case_id": result.test_case_id,
        "prompt_id": result.prompt_id,
        "config_id": result.config_id,
        "request_status": result.request_status,
        "response_status": result.response_status,
        "duration_seconds": result.duration_seconds,
        "output_tokens": result.output_tokens,
        "tokens_per_second": result.tokens_per_second,
        "response_chars": result.response_chars,
        "hit_token_limit": result.hit_token_limit,
        "python_compile_status": result.static_facts.python_compile_status,
    }
    return "<!-- BENCH_RESULT " + json.dumps(data, ensure_ascii=False, sort_keys=True) + " -->"


def render_model_result(result: ModelResult) -> str:
    raw = result.raw_ollama or {}
    metrics = [
        ["run_id", result.run_id],
        ["test_case_id", result.test_case_id],
        ["prompt_id", result.prompt_id],
        ["config_id", result.config_id],
        ["model_name", result.model_name],
        ["request_status", result.request_status],
        ["response_status", result.response_status],
        ["http_status_code", result.http_status_code],
        ["duration_seconds", f"{result.duration_seconds:.2f}" if result.duration_seconds is not None else ""],
        ["duration_hms", result.duration_hms],
        ["output_tokens", result.output_tokens],
        ["tokens_per_second", result.tokens_per_second],
        ["response_chars", result.response_chars],
        ["hit_token_limit", str(result.hit_token_limit).lower()],
        ["total_duration_ns", raw.get("total_duration")],
        ["load_duration_ns", raw.get("load_duration")],
        ["prompt_eval_count", raw.get("prompt_eval_count")],
        ["prompt_eval_duration_ns", raw.get("prompt_eval_duration")],
        ["eval_count", raw.get("eval_count")],
        ["eval_duration_ns", raw.get("eval_duration")],
    ]

    facts = result.static_facts
    facts_rows = [
        ["code_block_count", facts.code_block_count],
        ["extracted_python_chars", facts.extracted_python_chars],
        ["extracted_python_lines", facts.extracted_python_lines],
        ["python_compile_status", facts.python_compile_status],
        ["python_compile_error", short_error(facts.python_compile_error, 600)],
    ]

    parts = []
    parts.append(result_to_bench_comment(result))
    parts.append(f"\n### MODEL_RESULT: {result.model_name}\n")
    parts.append(md_table(["Метрика", "Значение"], metrics))
    parts.append("\n\n#### Raw static facts\n")
    parts.append(md_table(["Факт", "Значение"], facts_rows))

    if result.error_text:
        parts.append("\n\n#### Error\n")
        parts.append(fence(result.error_text, "text"))

    parts.append("\n\n#### Model response\n")
    parts.append(fence(result.response_text, "text"))

    parts.append("\n\n#### Human/AI notes\n")
    parts.append(fence("Заполни этот блок позже при ручной или AI-оценке.", "text"))
    parts.append("\n")
    return "".join(parts)


def render_run_report(
    *,
    run: str,
    args: argparse.Namespace,
    config: Dict[str, Any],
    config_id: str,
    models: Sequence[str],
    test_cases: Sequence[TestCase],
    pull_records: Sequence[PullRecord],
    results_by_test: Dict[str, List[ModelResult]],
    log_path: Path,
    report_path: Path,
) -> str:
    node_version = command_output(["node", "--version"])
    npm_version = command_output(["npm", "--version"])
    git_version = command_output(["git", "--version"])
    ollama_version = command_output([ollama_executable(), "--version"])

    metadata_rows = [
        ["Дата запуска", now_str()],
        ["Script version", SCRIPT_VERSION],
        ["Script path", Path(__file__).resolve()],
        ["Work dir", Path.cwd()],
        ["Technical log", log_path],
        ["AI report", report_path],
        ["Ollama URL", args.ollama_url],
        ["Python executable", sys.executable],
        ["Python version", sys.version.replace("\n", " ")],
        ["Platform", platform.platform()],
        ["Processor", platform.processor()],
        ["Machine", platform.machine()],
        ["Ollama version", ollama_version],
        ["Node.js version", node_version],
        ["npm version", npm_version],
        ["Git version", git_version],
        ["num_ctx", config["num_ctx"]],
        ["num_predict", config["num_predict"]],
        ["temperature", config["temperature"]],
        ["timeout_seconds", config["timeout_seconds"]],
        ["keep_alive", config["keep_alive"]],
        ["config_id", config_id],
        ["mode", "full" if args.full else "quick/custom"],
        ["models_count", len(models)],
        ["tests_count", len(test_cases)],
        ["skip_existing", not args.rerun_existing],
        ["pull_enabled", args.pull],
        ["model_source", getattr(args, "model_source", "installed")],
        ["pull_set", args.pull_set],
        ["explicit_models", "YES" if args.model else "NO"],
    ]

    parts: List[str] = []
    parts.append("\n\n---\n\n")
    parts.append(f"# RUN_ID: {run}\n\n")
    parts.append("## Run metadata\n\n")
    parts.append(md_table(["Поле", "Значение"], metadata_rows))

    parts.append("\n\n## Models in this run\n\n")
    parts.append(fence("\n".join(models), "text"))

    parts.append("\n\n## Generation config\n\n")
    parts.append(fence(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True), "json"))

    parts.append("\n\n## Model download phase before tests\n\n")
    if args.pull:
        rows = [[r.model, r.status, r.attempts, f"{r.duration_seconds:.2f}", short_error(r.error, 200)] for r in pull_records]
        parts.append(md_table(["model", "status", "attempts", "duration_sec", "error"], rows))
    else:
        parts.append("Download phase: `SKIPPED_BY_SCRIPT`. Если модели скачивались отдельно, это делал внешний PowerShell-wrapper или пользователь вручную.\n")

    parts.append("\n\n## Test cases in this run\n\n")
    rows = [[tc.test_case_id, tc.prompt_id, config_id, tc.title, tc.category] for tc in test_cases]
    parts.append(md_table(["test_case_id", "prompt_id", "config_id", "title", "category"], rows))

    for tc in test_cases:
        results = results_by_test.get(tc.test_case_id, [])
        parts.append(f"\n\n## TEST_CASE: {tc.test_case_id}\n\n")
        parts.append(f"**PROMPT_ID:** `{tc.prompt_id}`\n\n")
        parts.append(f"**CONFIG_ID:** `{config_id}`\n\n")
        parts.append(f"**Title:** {tc.title}\n\n")
        parts.append(f"**Category:** {tc.category}\n\n")
        parts.append("### Prompt\n\n")
        parts.append(fence(tc.prompt, "text"))

        parts.append("\n\n### Test raw summary table\n\n")
        summary_rows = []
        for r in results:
            summary_rows.append([
                r.model_name,
                r.request_status,
                r.response_status,
                f"{r.duration_seconds:.2f}" if r.duration_seconds is not None else "",
                r.output_tokens,
                r.tokens_per_second,
                r.response_chars,
                str(r.hit_token_limit).lower(),
                r.static_facts.python_compile_status,
                short_error(r.error_text, 100),
            ])
        parts.append(md_table([
            "model",
            "request_status",
            "response_status",
            "duration_sec",
            "tokens",
            "tokens_sec",
            "chars",
            "hit_token_limit",
            "py_compile",
            "error_short",
        ], summary_rows))

        for r in results:
            parts.append("\n")
            parts.append(render_model_result(r))

    parts.append("\n\n## RUN SUMMARY RAW METRICS\n\n")
    all_results = [r for result_list in results_by_test.values() for r in result_list]
    rows = []
    for r in all_results:
        rows.append([
            r.model_name,
            r.test_case_id,
            r.prompt_id,
            r.config_id,
            r.request_status,
            r.response_status,
            f"{r.duration_seconds:.2f}" if r.duration_seconds is not None else "",
            r.output_tokens,
            r.tokens_per_second,
            r.response_chars,
            str(r.hit_token_limit).lower(),
            r.static_facts.python_compile_status,
            short_error(r.error_text, 100),
        ])
    parts.append(md_table([
        "model",
        "test_case_id",
        "prompt_id",
        "config_id",
        "request_status",
        "response_status",
        "duration_sec",
        "tokens",
        "tokens_sec",
        "chars",
        "hit_token_limit",
        "py_compile",
        "error_short",
    ], rows))

    parts.append("\n\n## RUN ANALYSIS PROMPT\n\n")
    analysis_prompt = textwrap.dedent(f"""
        Проанализируй этот RUN_ID: {run}.

        Важно:
        - В отчёте нет автоматических оценок и рейтингов.
        - Не делай вывод только по скорости.
        - Оцени модели по полному ответу, ошибкам, соблюдению инструкции и пригодности к реальному coding agent.
        - Учитывай `hit_token_limit=true`: ответ мог быть обрезан лимитом токенов.
        - Учитывай `python_compile_status`: PASS означает только синтаксическую компиляцию, а не рабочую бизнес-логику.
        - `request_status=OK` означает только успешный HTTP-ответ Ollama, а не качество модели.

        Нужно выбрать лучшие локальные CPU-модели для кодинга.
        Оцени:
        1. качество кода
        2. полноту ответа
        3. выполнение инструкции
        4. скорость
        5. стабильность
        6. пригодность для Cline/Roo Code
        7. пригодность для задач Python + FastAPI + SQLite + Node.js + PowerShell + 1C/OData + RAG + Web scraping + поиск и обработка информации

        Сделай рейтинг моделей.
        Отдельно укажи:
        - лучшую основную модель
        - лучшую быструю модель
        - модель для сложных задач
        - модели, которые лучше удалить или не использовать
        - какие настройки `num_predict`/`num_ctx` стоит изменить для следующего теста
    """).strip()
    parts.append(fence(analysis_prompt, "text"))
    parts.append("\n")

    return "".join(parts)


# ----------------------------- test selection -----------------------------

def get_test_case_by_id(test_case_id: str) -> Optional[TestCase]:
    for tc in BUILTIN_TEST_CASES:
        if tc.test_case_id == test_case_id:
            return tc
    return None


def load_prompt_file(path: Path, custom_id: Optional[str] = None, title: Optional[str] = None) -> TestCase:
    prompt = path.read_text(encoding="utf-8")
    test_id_base = custom_id or f"custom_{path.stem}"
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]+", "_", test_id_base).strip("_") or "custom_prompt"
    return TestCase(
        test_case_id=safe_id,
        title=title or f"Custom prompt file: {path.name}",
        category="custom",
        prompt=prompt.strip(),
    )


def select_test_cases(args: argparse.Namespace) -> List[TestCase]:
    if args.prompt_file:
        return [load_prompt_file(Path(args.prompt_file), args.prompt_id, args.prompt_title)]

    if args.test_case:
        selected = []
        for tc_id in args.test_case:
            tc = get_test_case_by_id(tc_id)
            if tc is None:
                raise SystemExit(f"Unknown test case: {tc_id}. Use --list-tests.")
            selected.append(tc)
        return selected

    if args.full:
        return BUILTIN_TEST_CASES[:]

    return [BUILTIN_TEST_CASES[0]]


def select_models(args: argparse.Namespace) -> List[str]:
    """Select models for benchmark.

    v10 rule:
    - If --model is provided, use only explicitly provided models.
    - By default, read installed models from Ollama via /api/tags.
    - If --model-source set is used, use --pull-set / --model-set.
    - --all-installed is an alias for default installed behavior.
    """
    if args.model:
        return list(dict.fromkeys(args.model))

    if getattr(args, "all_installed", False):
        args.model_source = "installed"

    if getattr(args, "model_source", "installed") == "installed":
        try:
            models = get_ollama_models(args.ollama_url)
        except Exception as exc:
            raise SystemExit(f"Не удалось получить список моделей из Ollama: {exc}")
        if not models:
            raise SystemExit("В Ollama не найдено ни одной модели. Проверь: ollama list")
        return models

    selected_set = args.pull_set or args.model_set or "cpu"
    return MODEL_SETS[selected_set][:]


# ----------------------------- CLI -----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect raw Ollama CPU coding benchmark data into an AI-readable Markdown report. No automatic quality scores.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL), help="Ollama base URL")
    parser.add_argument("--model", action="append", help="Model to test. Can be used multiple times.")
    parser.add_argument("--model-source", choices=["installed", "set"], default="installed", help="Where to take models from when --model is not specified. Default: installed models from Ollama /api/tags.")
    parser.add_argument("--all-installed", action="store_true", help="Alias: test all installed models from Ollama. This is the default in v10.")
    parser.add_argument("--pull-set", choices=sorted(MODEL_SETS.keys()), default="cpu", help="Model set to use when --model-source set is selected")
    parser.add_argument("--model-set", choices=sorted(MODEL_SETS.keys()), help="Alias for --pull-set")
    parser.add_argument("--pull", action="store_true", help="Download/check selected models before benchmark inside Python")
    parser.add_argument("--no-pull", action="store_true", help="Compatibility flag. Pull is already disabled by default in v8.")
    parser.add_argument("--pull-attempts", type=int, default=3, help="Max ollama pull attempts when --pull is used")
    parser.add_argument("--full", action="store_true", help="Run all built-in test cases")
    parser.add_argument("--test-case", action="append", help="Run specific built-in test case id. Can be used multiple times.")
    parser.add_argument("--prompt-file", help="Path to one-time prompt file")
    parser.add_argument("--prompt-id", help="Custom test_case_id for --prompt-file, not PROMPT_ID hash")
    parser.add_argument("--prompt-title", help="Human title for --prompt-file")
    parser.add_argument("--list-tests", action="store_true", help="Show built-in test cases and PROMPT_IDs")
    parser.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX, help="Ollama num_ctx")
    parser.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT, help="Ollama num_predict")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Ollama temperature")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout per model/test")
    parser.add_argument("--keep-alive", default=DEFAULT_KEEP_ALIVE, help="Ollama keep_alive, e.g. 0s, 5m")
    parser.add_argument("--rerun-existing", action="store_true", help="Do not skip model+PROMPT_ID+CONFIG_ID already present in report")
    parser.add_argument("--no-syntax-check", action="store_true", help="Disable py_compile syntax facts")
    parser.add_argument("--log-file", default=LOG_FILENAME, help="Technical log file")
    parser.add_argument("--report-file", default=REPORT_FILENAME, help="AI-readable Markdown report file")
    parser.add_argument("--no-pause", action="store_true", help="Do not wait for Enter at the end")
    return parser


def print_tests() -> None:
    print("Built-in test cases:")
    for tc in BUILTIN_TEST_CASES:
        print(f"- {tc.test_case_id}")
        print(f"  title: {tc.title}")
        print(f"  category: {tc.category}")
        print(f"  prompt_id: {tc.prompt_id}")
    print("\nModel selection:")
    print("- default: installed models from Ollama (/api/tags)")
    print("- use --model-source set --pull-set <name> for fixed sets")
    print("\nModel sets:")
    for name, models in MODEL_SETS.items():
        print(f"- {name}: {', '.join(models)}")


# ----------------------------- main -----------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_tests:
        print_tests()
        return 0

    run = run_id()
    work_dir = Path.cwd()
    log_path = (work_dir / args.log_file).resolve()
    report_path = (work_dir / args.report_file).resolve()

    ensure_report_header(report_path)

    config = {
        "ollama_url": args.ollama_url.rstrip("/"),
        "num_ctx": args.num_ctx,
        "num_predict": args.num_predict,
        "temperature": args.temperature,
        "timeout_seconds": args.timeout_seconds,
        "keep_alive": args.keep_alive,
        "stream": False,
    }
    config_id = compute_config_id(config)

    models = select_models(args)
    test_cases = select_test_cases(args)

    print("=" * 72)
    print("Ollama CPU Coding Benchmark Collector")
    print("=" * 72)
    print(f"RUN_ID: {run}")
    print(f"CONFIG_ID: {config_id}")
    print(f"Log: {log_path}")
    print(f"Report: {report_path}")
    print(f"Models: {len(models)}")
    print(f"Model source: {getattr(args, 'model_source', 'installed')}")
    print(f"Tests: {len(test_cases)}")
    print("Automatic quality scores: DISABLED")
    print("=" * 72)

    log_line(log_path, run, "INFO", f"START | script={SCRIPT_VERSION} | config_id={config_id}")
    log_line(log_path, run, "INFO", f"MODELS | {', '.join(models)}")
    for tc in test_cases:
        log_line(log_path, run, "INFO", f"SELECTED_TEST | test={tc.test_case_id} | prompt_id={tc.prompt_id} | config_id={config_id}")

    # Test Ollama API early.
    try:
        installed_models = get_ollama_models(args.ollama_url)
        log_line(log_path, run, "OK", f"OLLAMA API OK | installed_models={len(installed_models)}")
    except Exception as exc:
        log_line(log_path, run, "ERROR", f"OLLAMA API ERROR | {short_error(str(exc))}")
        print("\nНе удалось подключиться к Ollama API.")
        print(f"Проверь, что Ollama запущен: {args.ollama_url}")
        if not args.no_pause:
            input("Нажми Enter для выхода...")
        return 1

    pull_records: List[PullRecord] = []
    if args.pull:
        for idx, model in enumerate(models, 1):
            print(f"\n[{idx}/{len(models)}] Подготовка модели: {model}")
            pull_records.append(pull_model(model, max_attempts=args.pull_attempts, log_path=log_path, run=run))

        # Test only models that were pulled successfully.
        ok_models = [r.model for r in pull_records if r.status == "OK"]
        if ok_models:
            models = ok_models
        else:
            log_line(log_path, run, "ERROR", "No models successfully pulled; benchmark aborted")
            print("Нет успешно подготовленных моделей. Тестирование отменено.")
            if not args.no_pause:
                input("Нажми Enter для выхода...")
            return 1
    else:
        log_line(log_path, run, "INFO", "PULL SKIPPED | Use PowerShell-wrapper for interactive download progress")

    existing = parse_existing_results(report_path)
    log_line(log_path, run, "INFO", f"EXISTING_RESULTS | count={len(existing)}")

    results_by_test: Dict[str, List[ModelResult]] = {}
    syntax_check = not args.no_syntax_check

    for tc_idx, tc in enumerate(test_cases, 1):
        print("\n" + "=" * 72)
        print(f"TEST {tc_idx}/{len(test_cases)}: {tc.test_case_id}")
        print(f"PROMPT_ID: {tc.prompt_id}")
        print(f"CONFIG_ID: {config_id}")
        print("=" * 72)
        print(tc.prompt)
        print("=" * 72)

        test_results: List[ModelResult] = []
        for model_idx, model in enumerate(models, 1):
            key = (model, tc.prompt_id, config_id)
            if not args.rerun_existing and key in existing:
                log_line(log_path, run, "INFO", f"SKIP_EXISTING | model={model} | prompt_id={tc.prompt_id} | config_id={config_id}")
                print(f"[{model_idx}/{len(models)}] SKIP: {model} уже есть для PROMPT_ID+CONFIG_ID")
                test_results.append(ModelResult(
                    run_id=run,
                    test_case_id=tc.test_case_id,
                    prompt_id=tc.prompt_id,
                    config_id=config_id,
                    model_name=model,
                    request_status="SKIPPED",
                    response_status="SKIPPED",
                    error_text="Existing result found in report for model+prompt_id+config_id.",
                ))
                continue

            print(f"\n[{model_idx}/{len(models)}] Модель: {model}")
            result = run_ollama_generate(
                run=run,
                test_case=tc,
                model=model,
                config_id=config_id,
                config=config,
                ollama_url=args.ollama_url,
                timeout_seconds=args.timeout_seconds,
                syntax_check=syntax_check,
                log_path=log_path,
            )
            test_results.append(result)
            print(
                f"Готово: request={result.request_status}, response={result.response_status}, "
                f"time={result.duration_hms}, tokens={result.output_tokens}, "
                f"chars={result.response_chars}, hit_limit={result.hit_token_limit}, "
                f"py_compile={result.static_facts.python_compile_status}"
            )

        results_by_test[tc.test_case_id] = test_results

    run_report = render_run_report(
        run=run,
        args=args,
        config=config,
        config_id=config_id,
        models=models,
        test_cases=test_cases,
        pull_records=pull_records,
        results_by_test=results_by_test,
        log_path=log_path,
        report_path=report_path,
    )
    write_text_append(report_path, run_report)

    log_line(log_path, run, "OK", f"FINISH | report={report_path}")

    print("\n" + "=" * 72)
    print("ГОТОВО")
    print(f"RUN_ID: {run}")
    print(f"CONFIG_ID: {config_id}")
    print(f"Лог: {log_path}")
    print(f"AI-readable отчёт: {report_path}")
    print("Автоматических оценок и рейтингов нет. В отчёте только факты.")
    print("=" * 72)

    if not args.no_pause:
        input("Нажми Enter для выхода...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
