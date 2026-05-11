#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
model_performance_test_v7.py

Назначение:
    Benchmark локальных Ollama-моделей для CPU-кодинга.

Что делает:
    1. Автоматически проверяет/устанавливает Python-модуль requests.
    2. Получает список моделей из Ollama.
    3. Создаёт уникальный RUN_ID для каждого запуска.
    4. Пишет технический лог в один общий файл:
       model_performance_test.log
    5. Пишет AI-readable Markdown-отчёт в один общий файл:
       model_benchmark_ai_report.md
    6. Сохраняет полный prompt, полный ответ модели, метрики скорости и автопроверки.
    7. Вычисляет стабильный PROMPT_ID для каждого prompt.
    8. Пишет PROMPT_ID в технический лог и Markdown-отчёт.
    9. По умолчанию пропускает повторный запуск той же пары model + PROMPT_ID,
       если такой успешный тест уже есть в model_benchmark_ai_report.md.
    10. В конце печатает таблицу рейтинга текущего запуска.

Базовый запуск:
    py .\model_performance_test_v7.py

Полный набор тестов:
    py .\model_performance_test_v7.py --full

Только одна модель:
    py .\model_performance_test_v7.py --model qwen2.5-coder:3b

Несколько моделей:
    py .\model_performance_test_v7.py --model qwen2.5-coder:3b --model codegemma:2b

Только список моделей, которые будут подготовлены перед тестом:
    py .\model_performance_test_v7.py --list-models

Только список уже установленных моделей без скачивания:
    py .\model_performance_test_v7.py --list-models --no-pull

Подготовить и тестировать конкретные модели:
    py .\model_performance_test_v7.py --model qwen2.5-coder:3b --model codegemma:2b

Отключить скачивание перед тестом:
    py .\model_performance_test_v7.py --no-pull

Только список тестов:
    py .\model_performance_test_v7.py --list-tests

Показать prompts без запуска моделей:
    py .\model_performance_test_v7.py --dry-run

Важно:
    Скрипт не создаёт отдельные файлы на каждый запуск.
    Он дописывает новые результаты в:
        - model_performance_test.log
        - model_benchmark_ai_report.md
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
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


SCRIPT_VERSION = "v7.0"
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
DEFAULT_NUM_CTX = 2048
DEFAULT_NUM_PREDICT = 700
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_PULL_RETRIES = 3
DEFAULT_PULL_SET = "cpu"
PULL_MODEL_SETS: Dict[str, Tuple[str, ...]] = {
    # Минимальный быстрый набор для проверки идеи.
    "quick": (
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:3b",
        "codegemma:2b",
    ),
    # Основной CPU-набор: маленькие и средние модели для локального кодинга.
    "cpu": (
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:3b",
        "codegemma:2b",
        "deepseek-coder:1.3b",
        "starcoder2:3b",
        "granite-code:3b",
        "stable-code:3b",
        "yi-coder:1.5b",
        "llama3.2:3b",
        "phi3:mini",
    ),
    # Тяжёлые 6.7B/7B модели. На CPU могут быть медленными, но полезны для сравнения качества.
    "heavy": (
        "qwen2.5-coder:7b",
        "deepseek-coder:6.7b",
        "codellama:7b-instruct",
        "mistral:7b-instruct-v0.3",
    ),
}
PULL_MODEL_SETS["all"] = tuple(dict.fromkeys(PULL_MODEL_SETS["cpu"] + PULL_MODEL_SETS["heavy"]))

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_PATH = SCRIPT_DIR / "model_performance_test.log"
AI_REPORT_PATH = SCRIPT_DIR / "model_benchmark_ai_report.md"


def _print_install_message(message: str) -> None:
    print(f"[DEPENDENCY] {message}", flush=True)


def ensure_package(package_name: str, import_name: Optional[str] = None) -> None:
    """
    Проверяет наличие Python-пакета и пытается установить его через pip, если его нет.
    Это должно выполняться до импорта внешних модулей.
    """
    module_name = import_name or package_name
    if importlib.util.find_spec(module_name) is not None:
        return

    _print_install_message(f"Модуль '{module_name}' не найден. Пробую установить пакет '{package_name}'...")

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "--version"])
    except Exception:
        _print_install_message("pip не найден. Пробую включить ensurepip...")
        try:
            subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
        except Exception as exc:
            raise RuntimeError(
                f"Не удалось включить pip через ensurepip. Ошибка: {exc}"
            ) from exc

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    except Exception as exc:
        raise RuntimeError(
            f"Не удалось установить пакет '{package_name}'. Ошибка: {exc}"
        ) from exc

    if importlib.util.find_spec(module_name) is None:
        raise RuntimeError(
            f"Пакет '{package_name}' установлен, но модуль '{module_name}' всё ещё не импортируется."
        )


ensure_package("requests", "requests")
import requests  # noqa: E402


@dataclass(frozen=True)
class TestCase:
    test_case_id: str
    title: str
    category: str
    prompt: str
    expected_keywords: Tuple[str, ...]


@dataclass
class ModelResult:
    run_id: str
    test_case_id: str
    prompt_id: str
    model_name: str
    status: str
    duration_seconds: float
    response_text: str
    response_chars: int
    output_tokens: Optional[int]
    tokens_per_second: Optional[float]
    total_duration_ns: Optional[int]
    load_duration_ns: Optional[int]
    prompt_eval_count: Optional[int]
    prompt_eval_duration_ns: Optional[int]
    eval_count: Optional[int]
    eval_duration_ns: Optional[int]
    error_text: str
    http_status_code: Optional[int]
    auto_checks: List[Tuple[str, str, float, str]]
    auto_quality_score: float
    speed_score: float
    stability_score: float
    score_total: float


@dataclass
class PullResult:
    model_name: str
    status: str
    attempts: int
    duration_seconds: float
    error_text: str


def now_str() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_run_id() -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
    return f"RUN-{stamp}-{suffix}"


def normalize_prompt_for_id(prompt: str) -> str:
    """
    Нормализует prompt перед хешированием.

    Важно: нормализация убирает различия Windows/Linux переводов строк и лишние
    пробелы в конце строк, но не меняет смысл prompt.
    Поэтому один и тот же prompt получает один и тот же PROMPT_ID.
    """
    text = (prompt or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.strip().split("\n")]
    return "\n".join(lines).strip()


def make_prompt_id(prompt: str, prefix: str = "PROMPT") -> str:
    normalized = normalize_prompt_for_id(prompt)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()
    return f"{prefix}-{digest[:16]}"


def make_test_prompt_id(test_case: "TestCase") -> str:
    return make_prompt_id(test_case.prompt)


def format_seconds(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    return str(_dt.timedelta(seconds=round(seconds)))


def safe_round(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return ""
    try:
        return str(round(float(value), digits))
    except Exception:
        return ""


def write_text_append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(text)


def log_line(run_id: str, message: str, level: str = "INFO") -> None:
    line = f"[{now_str()}] [{level}] [{run_id}] {message}"
    print(line, flush=True)
    write_text_append(LOG_PATH, line + "\n")


def run_command_version(command: Sequence[str], timeout: int = 5) -> str:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        if completed.returncode != 0 and not output:
            return f"ERROR: return code {completed.returncode}"
        return output.splitlines()[0] if output else f"return code {completed.returncode}"
    except FileNotFoundError:
        return "NOT INSTALLED"
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as exc:
        return f"ERROR: {exc}"


def get_environment_info(ollama_url: str) -> Dict[str, str]:
    return {
        "datetime": now_str(),
        "script_version": SCRIPT_VERSION,
        "script_path": str(Path(__file__).resolve()),
        "work_dir": str(Path.cwd()),
        "python_executable": sys.executable,
        "python_version": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "processor": platform.processor() or "",
        "machine": platform.machine(),
        "ollama_url": ollama_url,
        "ollama_version": run_command_version(["ollama", "--version"]),
        "node_version": run_command_version(["node", "--version"]),
        "npm_version": run_command_version(["npm", "--version"]),
        "git_version": run_command_version(["git", "--version"]),
    }


def check_ollama_server(ollama_url: str, timeout: int = 10) -> bool:
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def get_models(ollama_url: str, timeout: int = 10) -> List[str]:
    response = requests.get(f"{ollama_url}/api/tags", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    models = []
    for item in data.get("models", []):
        name = item.get("name")
        if name:
            models.append(name)
    return sorted(models, key=lambda x: x.lower())



def sanitize_terminal_output(text: str, max_chars: int = 4000) -> str:
    """Убирает ANSI/VT мусор из вывода CLI и оставляет короткий диагностический хвост."""
    if not text:
        return ""
    ansi_pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    cleaned = ansi_pattern.sub("", text)
    cleaned = cleaned.replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[-max_chars:]
    return cleaned


def load_existing_benchmark_index(report_path: Path) -> List[Dict[str, Any]]:
    """
    Читает Markdown-отчёт и вытаскивает machine-readable BENCH_RESULT-маркеры.

    Маркер выглядит так:
    <!-- BENCH_RESULT {"run_id":"...","prompt_id":"...","model_name":"...","status":"OK"} -->

    Это Markdown-комментарий: он не мешает человеку и ИИ читать файл, но скрипт
    может быстро понять, какие model + PROMPT_ID уже тестировались.
    """
    if not report_path.exists():
        return []

    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    pattern = re.compile(r"<!--\s*BENCH_RESULT\s+(\{.*?\})\s*-->", re.DOTALL)
    items: List[Dict[str, Any]] = []
    for match in pattern.finditer(text):
        raw_json = match.group(1)
        try:
            item = json.loads(raw_json)
            if isinstance(item, dict):
                items.append(item)
        except Exception:
            continue
    return items


def should_skip_existing_result(
    existing_index: Sequence[Dict[str, Any]],
    model_name: str,
    prompt_id: str,
    skip_any_existing: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Возвращает найденную старую запись, если текущий тест нужно пропустить.

    По умолчанию пропускаем только ранее успешные OK-запуски.
    Если включён --skip-any-existing, пропускаем любую старую запись с той же
    парой model + PROMPT_ID, даже ERROR/TIMEOUT.
    """
    for item in existing_index:
        if str(item.get("model_name", "")) != model_name:
            continue
        if str(item.get("prompt_id", "")) != prompt_id:
            continue

        status = str(item.get("status", ""))
        if skip_any_existing or status == "OK":
            return item
    return None


def add_result_to_existing_index(existing_index: List[Dict[str, Any]], result: "ModelResult") -> None:
    existing_index.append(
        {
            "run_id": result.run_id,
            "test_case_id": result.test_case_id,
            "prompt_id": result.prompt_id,
            "model_name": result.model_name,
            "status": result.status,
        }
    )


def unique_preserve_order(items: Sequence[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def build_pull_targets(args: argparse.Namespace) -> List[str]:
    """
    Список моделей, которые нужно гарантированно скачать перед тестированием.

    Логика:
    - если пользователь указал --model, считаем, что именно эти модели надо скачать и тестировать;
    - если --model не указан, берём набор из --pull-set;
    - --pull-model добавляет дополнительные модели к скачиванию;
    - --exclude-model исключает модели из скачивания;
    - --limit-models ограничивает список, чтобы не тянуть слишком много за один запуск.
    """
    targets: List[str] = []

    if args.model:
        targets.extend(args.model)
    else:
        targets.extend(PULL_MODEL_SETS.get(args.pull_set, PULL_MODEL_SETS[DEFAULT_PULL_SET]))

    if args.pull_model:
        targets.extend(args.pull_model)

    targets = unique_preserve_order(targets)

    if args.exclude_model:
        excludes = [x.lower() for x in args.exclude_model]
        targets = [m for m in targets if not any(ex in m.lower() for ex in excludes)]

    if args.limit_models is not None:
        targets = targets[: args.limit_models]

    return targets


def is_model_installed(installed_models: Sequence[str], model_name: str) -> bool:
    return model_name in installed_models


def remove_model_if_possible(run_id: str, model_name: str) -> None:
    """Удаляет возможную битую/неполную модель. Ошибки игнорируются."""
    try:
        completed = subprocess.run(
            ["ollama", "rm", model_name],
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )
        if completed.returncode == 0:
            log_line(run_id, f"Удалил модель перед повторной загрузкой: {model_name}", "WARN")
    except Exception as exc:
        log_line(run_id, f"Не удалось выполнить ollama rm {model_name}: {exc}", "WARN")


def pull_one_model(run_id: str, model_name: str, retries: int = DEFAULT_PULL_RETRIES) -> PullResult:
    """
    Скачивает модель через `ollama pull` перед benchmark.

    Специально не выводит сырой прогресс Ollama в консоль, потому что старый PowerShell
    плохо обрабатывает VT/ANSI-последовательности. Вместо этого показывает чистый heartbeat.
    Полный вывод попытки пишется во временный файл и используется только для диагностики ошибки.
    """
    started = time.perf_counter()
    last_error = ""

    for attempt in range(1, retries + 1):
        attempt_started = time.perf_counter()
        log_line(run_id, f"PULL START | model={model_name} | attempt={attempt}/{retries}")
        print(f"\nСкачивание модели: {model_name} | попытка {attempt} из {retries}", flush=True)
        print("Сырой прогресс Ollama скрыт, чтобы не засорять PowerShell. Жди статус...", flush=True)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix="ollama_pull_",
                suffix=".log",
                delete=False,
            ) as tmp:
                tmp_path = tmp.name
                proc = subprocess.Popen(
                    ["ollama", "pull", model_name],
                    stdout=tmp,
                    stderr=subprocess.STDOUT,
                    shell=False,
                )

                last_heartbeat = 0.0
                while proc.poll() is None:
                    elapsed = time.perf_counter() - attempt_started
                    if elapsed - last_heartbeat >= 15:
                        print(f"  {model_name}: скачивается... прошло {int(elapsed)} сек", flush=True)
                        last_heartbeat = elapsed
                    time.sleep(1)

                return_code = proc.returncode

            raw_output = ""
            if tmp_path:
                try:
                    raw_output = Path(tmp_path).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    raw_output = ""

            clean_output = sanitize_terminal_output(raw_output)
            attempt_seconds = time.perf_counter() - attempt_started

            if return_code == 0:
                total_seconds = time.perf_counter() - started
                log_line(
                    run_id,
                    f"PULL OK | model={model_name} | attempt={attempt}/{retries} | seconds={safe_round(attempt_seconds)}",
                    "OK",
                )
                print(f"OK: {model_name} скачана/проверена за {format_seconds(attempt_seconds)}", flush=True)
                return PullResult(
                    model_name=model_name,
                    status="OK",
                    attempts=attempt,
                    duration_seconds=total_seconds,
                    error_text="",
                )

            last_error = clean_output or f"ollama pull завершился с кодом {return_code}"
            log_line(
                run_id,
                f"PULL ERROR | model={model_name} | attempt={attempt}/{retries} | code={return_code} | error={last_error[:1000]}",
                "ERROR",
            )
            print(f"ОШИБКА скачивания {model_name}: попытка {attempt} из {retries}", flush=True)

            # При digest mismatch / битой загрузке / любой ошибке безопаснее убрать модель и повторить.
            remove_model_if_possible(run_id, model_name)

            if attempt < retries:
                print("Пробую повторить через 5 секунд...", flush=True)
                time.sleep(5)

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            last_error = f"Exception during ollama pull: {exc}\n{traceback.format_exc()}"
            log_line(run_id, f"PULL EXCEPTION | model={model_name} | attempt={attempt}/{retries} | {exc}", "ERROR")
            remove_model_if_possible(run_id, model_name)
            if attempt < retries:
                time.sleep(5)
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    total_seconds = time.perf_counter() - started
    print(f"FAIL: {model_name} не скачалась после {retries} попыток", flush=True)
    return PullResult(
        model_name=model_name,
        status="ERROR",
        attempts=retries,
        duration_seconds=total_seconds,
        error_text=last_error,
    )


def pull_models_before_test(run_id: str, model_names: Sequence[str], retries: int) -> List[PullResult]:
    results: List[PullResult] = []
    if not model_names:
        return results

    print("\n" + "=" * 90)
    print("ЭТАП 1: СКАЧИВАНИЕ/ПРОВЕРКА МОДЕЛЕЙ OLLAMA")
    print("=" * 90)
    print(f"Моделей к проверке: {len(model_names)}")
    for idx, name in enumerate(model_names, start=1):
        print(f"  {idx}. {name}")
    print("=" * 90)

    log_line(run_id, f"Pull phase started. models_count={len(model_names)} retries={retries}")

    for idx, model_name in enumerate(model_names, start=1):
        print(f"\n[{idx}/{len(model_names)}] Подготовка модели: {model_name}", flush=True)
        result = pull_one_model(run_id, model_name, retries=retries)
        results.append(result)

    ok_count = sum(1 for r in results if r.status == "OK")
    error_count = len(results) - ok_count
    log_line(run_id, f"Pull phase finished. ok={ok_count} errors={error_count}")

    print("\n" + "=" * 90)
    print("ИТОГ СКАЧИВАНИЯ МОДЕЛЕЙ")
    print("=" * 90)
    for result in results:
        print(
            f"{result.model_name:35} | {result.status:5} | "
            f"attempts={result.attempts} | time={format_seconds(result.duration_seconds)}"
        )
    print("=" * 90 + "\n")

    return results


def unload_model(ollama_url: str, model_name: str, timeout: int = 30) -> None:
    """
    Ollama unload: передаём keep_alive=0.
    Если версия Ollama не поддерживает такую выгрузку, ошибка игнорируется.
    """
    try:
        requests.post(
            f"{ollama_url}/api/generate",
            json={"model": model_name, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=timeout,
        )
    except Exception:
        pass


def build_test_cases() -> List[TestCase]:
    return [
        TestCase(
            test_case_id="fastapi_sqlite_node_health",
            title="FastAPI + SQLite + Node.js health endpoint",
            category="backend",
            expected_keywords=(
                "fastapi",
                "sqlite",
                "health",
                "node",
                "subprocess",
                "uvicorn",
            ),
            prompt=textwrap.dedent(
                """
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
                """
            ).strip(),
        ),
        TestCase(
            test_case_id="python_sqlite_bugfix",
            title="Python SQLite bug fixing",
            category="bugfix",
            expected_keywords=(
                "sqlite3",
                "connect",
                "commit",
                "close",
                "parameter",
                "try",
            ),
            prompt=textwrap.dedent(
                """
                Исправь код ниже и верни один полный исправленный файл Python.

                Задача:
                Код должен безопасно работать с SQLite, создавать таблицу clients,
                добавлять клиента и искать клиента по телефону.
                Нужно исправить ошибки, SQL-инъекцию, отсутствие commit/close,
                неправильную обработку пустого результата.

                Исходный код с ошибками:

                import sqlite3

                DB = "clients.db"

                def init_db():
                    conn = sqlite3.connect(DB)
                    cur = conn.cursor()
                    cur.execute("CREATE TABLE clients id INTEGER PRIMARY KEY, name TEXT, phone TEXT UNIQUE")
                    conn.close

                def add_client(name, phone):
                    conn = sqlite3.connect(DB)
                    cur = conn.cursor()
                    sql = "INSERT INTO clients(name, phone) VALUES ('" + name + "', '" + phone + "')"
                    cur.execute(sql)
                    return True

                def find_client(phone):
                    conn = sqlite3.connect(DB)
                    cur = conn.cursor()
                    cur.execute("SELECT id, name, phone FROM clients WHERE phone = " + phone)
                    row = cur.fetchone()
                    return {"id": row[0], "name": row[1], "phone": row[2]}

                if __name__ == "__main__":
                    init_db()
                    add_client("Ali", "+77010000000")
                    print(find_client("+77010000000"))

                Требования:
                1. Верни полный исправленный Python-файл.
                2. Используй параметризованные SQL-запросы.
                3. Используй with sqlite3.connect(...) или гарантированное закрытие соединения.
                4. При дубликате телефона не падай некрасивой ошибкой.
                5. Если клиент не найден, верни None.
                6. Не пиши объяснения, верни только код.
                """
            ).strip(),
        ),
        TestCase(
            test_case_id="sqlite_analytics_queries",
            title="SQLite schema and analytics queries",
            category="database",
            expected_keywords=(
                "CREATE TABLE",
                "clients",
                "cars",
                "visits",
                "SELECT",
                "JOIN",
                "GROUP BY",
            ),
            prompt=textwrap.dedent(
                """
                Напиши SQL-файл для SQLite.

                Предметная область:
                Автомойка. Нужно хранить клиентов, автомобили и посещения.

                Требования:
                1. Создай таблицу clients.
                2. Создай таблицу cars.
                3. Создай таблицу visits.
                4. Свяжи cars с clients.
                5. Свяжи visits с cars.
                6. Добавь индексы для plate и visit_time.
                7. Напиши минимум 5 аналитических SELECT-запросов:
                   - список посещений за период
                   - топ автомобилей по количеству посещений
                   - последний визит каждого автомобиля
                   - выручка по дням
                   - поиск по госномеру
                8. Используй SQLite-синтаксис.
                9. Верни только SQL, без объяснений.
                """
            ).strip(),
        ),
        TestCase(
            test_case_id="powershell_fastapi_launcher",
            title="PowerShell launcher for FastAPI project",
            category="windows",
            expected_keywords=(
                "powershell",
                "venv",
                "pip",
                "fastapi",
                "uvicorn",
                "8010",
            ),
            prompt=textwrap.dedent(
                """
                Напиши полный PowerShell-скрипт run-fastapi-local.ps1 для Windows 10.

                Задача:
                Скрипт должен подготовить и запустить локальный FastAPI-проект.

                Требования:
                1. Проверить наличие Python через py или python.
                2. Создать .venv, если его нет.
                3. Активировать .venv.
                4. Обновить pip.
                5. Установить fastapi и uvicorn.
                6. Проверить наличие Node.js через node --version и вывести предупреждение, если его нет.
                7. Запустить сервер main.py на порту 8010.
                8. Писать понятные сообщения в консоль.
                9. В конце не закрывать окно сразу, если возникла ошибка.
                10. Верни только полный код PowerShell-скрипта.
                """
            ).strip(),
        ),
        TestCase(
            test_case_id="python_1c_odata_client",
            title="Python 1C OData client",
            category="integration",
            expected_keywords=(
                "requests",
                "OData",
                "BasicAuth",
                "filter",
                "timeout",
                "raise",
            ),
            prompt=textwrap.dedent(
                """
                Напиши один полный Python-файл odata_1c_client.py.

                Контекст:
                Нужно подключаться к 1С через OData HTTP API.

                Требования:
                1. Используй requests.
                2. Сделай класс OData1CClient.
                3. Конструктор принимает:
                   - base_url
                   - username
                   - password
                   - timeout
                4. Реализуй метод get_counterparties(limit=50, name_contains=None).
                5. Метод должен делать GET к справочнику контрагентов.
                6. Поддержи OData-параметры:
                   - $top
                   - $filter
                   - $format=json
                7. Корректно кодируй query params через requests params, не собирай URL руками.
                8. Обрабатывай HTTP-ошибки.
                9. Возвращай список элементов из JSON.
                10. Добавь пример использования в блоке if __name__ == "__main__".
                11. Верни только полный код Python-файла, без объяснений.
                """
            ).strip(),
        ),
    ]


def normalize_text(text: str) -> str:
    return text.lower().replace("\r\n", "\n").replace("\r", "\n")


def contains_any(text: str, variants: Sequence[str]) -> bool:
    t = normalize_text(text)
    return any(v.lower() in t for v in variants)


def contains_regex(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL) is not None


def add_check(
    checks: List[Tuple[str, str, float, str]],
    name: str,
    condition: bool,
    points: float,
    comment_ok: str = "",
    comment_fail: str = "",
) -> None:
    checks.append((name, "YES" if condition else "NO", points if condition else 0.0, comment_ok if condition else comment_fail))


def auto_check_response(test_case: TestCase, response_text: str, status: str, duration_seconds: float) -> Tuple[List[Tuple[str, str, float, str]], float]:
    checks: List[Tuple[str, str, float, str]] = []
    if status != "OK":
        checks.append(("status_ok", "NO", 0.0, "Модель не вернула успешный ответ."))
        return checks, 0.0

    text = response_text or ""
    t = normalize_text(text)
    test_id = test_case.test_case_id

    if test_id == "fastapi_sqlite_node_health":
        add_check(checks, "contains_fastapi_import", "fastapi" in t and ("fastapi(" in t or "from fastapi" in t), 1.3)
        add_check(checks, "contains_sqlite", "sqlite3" in t or "sqlite" in t, 1.2)
        add_check(checks, "contains_cars_table", "create table" in t and "cars" in t and "plate" in t, 1.0)
        add_check(checks, "contains_post_cars", contains_regex(t, r"@app\.(post|api_route)\([\"']/cars"), 1.0)
        add_check(checks, "contains_get_cars", contains_regex(t, r"@app\.get\([\"']/cars[\"']") or '"/cars"' in t, 0.8)
        add_check(checks, "contains_get_cars_plate", "{plate}" in t or "<plate>" in t, 0.8)
        add_check(checks, "contains_health_endpoint", "/health" in t, 1.0)
        add_check(checks, "contains_node_check", "node --version" in t or ("node" in t and "subprocess" in t), 1.0)
        add_check(checks, "contains_pydantic_model", "basemodel" in t or "pydantic" in t, 0.7)
        add_check(checks, "contains_http_exception", "httpexception" in t, 0.6)
        add_check(checks, "contains_uvicorn_main", "uvicorn.run" in t and "__main__" in t, 0.6)

    elif test_id == "python_sqlite_bugfix":
        add_check(checks, "contains_sqlite3", "sqlite3" in t, 1.2)
        add_check(checks, "creates_valid_table", "create table" in t and "clients" in t and "id integer primary key" in t, 1.2)
        add_check(checks, "uses_parameterized_sql", "?" in text and "execute(" in t, 1.6)
        add_check(checks, "handles_duplicate", "integrityerror" in t or "unique" in t or "duplicate" in t, 1.1)
        add_check(checks, "returns_none_when_not_found", "none" in t and "if row" in t, 1.0)
        add_check(checks, "uses_commit", ".commit(" in t or "with sqlite3.connect" in t, 1.0)
        add_check(checks, "closes_connection_or_context", "with sqlite3.connect" in t or ".close(" in t, 1.1)
        add_check(checks, "has_main_block", "__main__" in t, 0.8)
        add_check(checks, "no_obvious_bad_string_sql", "' + phone" not in t and '"+ phone' not in t and "+ phone" not in t, 1.0)

    elif test_id == "sqlite_analytics_queries":
        add_check(checks, "creates_clients", "create table" in t and "clients" in t, 1.0)
        add_check(checks, "creates_cars", "create table" in t and "cars" in t, 1.0)
        add_check(checks, "creates_visits", "create table" in t and "visits" in t, 1.0)
        add_check(checks, "has_foreign_keys", "foreign key" in t or "references" in t, 1.0)
        add_check(checks, "has_indexes", "create index" in t, 1.0)
        select_count = len(re.findall(r"\bselect\b", t))
        add_check(checks, "has_at_least_5_selects", select_count >= 5, 1.5, f"SELECT count: {select_count}", f"SELECT count: {select_count}")
        add_check(checks, "uses_join", " join " in t, 1.0)
        add_check(checks, "uses_group_by", "group by" in t, 1.0)
        add_check(checks, "has_plate_search", "plate" in t and ("where" in t or "like" in t), 0.8)
        add_check(checks, "has_revenue_query", "sum(" in t or "revenue" in t or "amount" in t or "price" in t, 0.7)

    elif test_id == "powershell_fastapi_launcher":
        add_check(checks, "looks_like_powershell", "$" in text or "param(" in t or "powershell" in t, 1.0)
        add_check(checks, "checks_python", "py " in t or "python" in t, 1.0)
        add_check(checks, "creates_venv", "venv" in t and ("-m venv" in t or ".venv" in t), 1.2)
        add_check(checks, "activates_venv", "activate.ps1" in t or "scripts\\activate" in t or "scripts/activate" in t, 1.0)
        add_check(checks, "installs_fastapi_uvicorn", "pip" in t and "fastapi" in t and "uvicorn" in t, 1.2)
        add_check(checks, "checks_node", "node --version" in t or "node" in t, 1.0)
        add_check(checks, "uses_port_8010", "8010" in t, 1.0)
        add_check(checks, "handles_errors", "try" in t or "$lastexitcode" in t or "catch" in t or "erroraction" in t, 1.2)
        add_check(checks, "keeps_window_on_error", "read-host" in t or "pause" in t, 0.8)
        add_check(checks, "runs_server", "uvicorn" in t or "main:app" in t or "main.py" in t, 0.6)

    elif test_id == "python_1c_odata_client":
        add_check(checks, "uses_requests", "requests" in t, 1.0)
        add_check(checks, "defines_client_class", "class odata1cclient" in t.replace("_", ""), 1.0)
        add_check(checks, "uses_auth", "auth" in t and ("username" in t or "password" in t), 1.2)
        add_check(checks, "has_get_counterparties", "get_counterparties" in t, 1.2)
        add_check(checks, "uses_params_dict", "params" in t and "$top" in t and "$format" in t, 1.3)
        add_check(checks, "supports_filter", "$filter" in t or "filter" in t, 1.1)
        add_check(checks, "uses_timeout", "timeout" in t, 0.8)
        add_check(checks, "handles_http_errors", "raise_for_status" in t or "status_code" in t or "httperror" in t, 1.0)
        add_check(checks, "returns_json_values", "json()" in t and ("value" in t or "data" in t), 0.8)
        add_check(checks, "has_main_example", "__main__" in t, 0.6)

    else:
        for keyword in test_case.expected_keywords:
            add_check(checks, f"contains_{keyword}", keyword.lower() in t, 1.0)

    max_possible = sum(point for _, _, point, _ in checks)
    if max_possible <= 0:
        return checks, 0.0
    raw_score = sum(point for _, result, point, _ in checks if result == "YES")
    normalized_10 = min(10.0, max(0.0, (raw_score / max_possible) * 10.0))
    return checks, normalized_10


def calculate_speed_score(duration_seconds: float, tokens_per_second: Optional[float], status: str) -> float:
    if status != "OK":
        return 0.0

    if duration_seconds <= 30:
        duration_score = 10.0
    elif duration_seconds <= 60:
        duration_score = 8.0
    elif duration_seconds <= 120:
        duration_score = 6.0
    elif duration_seconds <= 240:
        duration_score = 4.0
    elif duration_seconds <= 600:
        duration_score = 2.0
    else:
        duration_score = 0.5

    if tokens_per_second is None:
        tps_score = 5.0
    elif tokens_per_second >= 20:
        tps_score = 10.0
    elif tokens_per_second >= 10:
        tps_score = 8.0
    elif tokens_per_second >= 5:
        tps_score = 6.0
    elif tokens_per_second >= 2:
        tps_score = 4.0
    else:
        tps_score = 2.0

    return round((duration_score * 0.6) + (tps_score * 0.4), 2)


def calculate_stability_score(status: str, response_text: str, error_text: str) -> float:
    if status != "OK":
        return 0.0
    if error_text:
        return 5.0
    if not response_text.strip():
        return 0.0
    if len(response_text.strip()) < 100:
        return 4.0
    return 10.0


def calculate_total_score(auto_quality_score: float, speed_score: float, stability_score: float) -> float:
    return round((auto_quality_score * 0.65) + (speed_score * 0.20) + (stability_score * 0.15), 2)


def run_model_test(
    run_id: str,
    ollama_url: str,
    model_name: str,
    test_case: TestCase,
    timeout_seconds: int,
    num_ctx: int,
    num_predict: int,
    temperature: float,
    unload_after_each_test: bool,
) -> ModelResult:
    prompt_id = make_test_prompt_id(test_case)

    payload = {
        "model": model_name,
        "prompt": test_case.prompt,
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "temperature": temperature,
        },
    }

    log_line(run_id, f"START | model={model_name} | test={test_case.test_case_id} | prompt_id={prompt_id}")

    start = time.perf_counter()
    status = "ERROR"
    response_text = ""
    error_text = ""
    http_status_code: Optional[int] = None
    data: Dict[str, Any] = {}

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json=payload,
            timeout=timeout_seconds,
        )
        http_status_code = response.status_code
        duration = time.perf_counter() - start

        if response.status_code == 200:
            try:
                data = response.json()
            except Exception as exc:
                status = "ERROR"
                error_text = f"JSON parse error: {exc}"
            else:
                status = "OK"
                response_text = data.get("response") or ""
                if not response_text.strip():
                    error_text = "Empty response text."
        else:
            status = "ERROR"
            error_text = f"HTTP {response.status_code}: {response.text[:1000]}"

    except requests.Timeout:
        duration = time.perf_counter() - start
        status = "TIMEOUT"
        error_text = f"Timeout after {timeout_seconds} seconds."
    except Exception as exc:
        duration = time.perf_counter() - start
        status = "ERROR"
        error_text = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    output_tokens = data.get("eval_count") if isinstance(data, dict) else None
    eval_duration_ns = data.get("eval_duration") if isinstance(data, dict) else None

    tokens_per_second: Optional[float] = None
    try:
        if output_tokens is not None and eval_duration_ns:
            seconds = float(eval_duration_ns) / 1_000_000_000
            if seconds > 0:
                tokens_per_second = float(output_tokens) / seconds
    except Exception:
        tokens_per_second = None

    auto_checks, auto_quality_score = auto_check_response(test_case, response_text, status, duration)
    speed_score = calculate_speed_score(duration, tokens_per_second, status)
    stability_score = calculate_stability_score(status, response_text, error_text)
    score_total = calculate_total_score(auto_quality_score, speed_score, stability_score)

    result = ModelResult(
        run_id=run_id,
        test_case_id=test_case.test_case_id,
        prompt_id=prompt_id,
        model_name=model_name,
        status=status,
        duration_seconds=duration,
        response_text=response_text,
        response_chars=len(response_text),
        output_tokens=output_tokens,
        tokens_per_second=tokens_per_second,
        total_duration_ns=data.get("total_duration") if isinstance(data, dict) else None,
        load_duration_ns=data.get("load_duration") if isinstance(data, dict) else None,
        prompt_eval_count=data.get("prompt_eval_count") if isinstance(data, dict) else None,
        prompt_eval_duration_ns=data.get("prompt_eval_duration") if isinstance(data, dict) else None,
        eval_count=data.get("eval_count") if isinstance(data, dict) else None,
        eval_duration_ns=data.get("eval_duration") if isinstance(data, dict) else None,
        error_text=error_text,
        http_status_code=http_status_code,
        auto_checks=auto_checks,
        auto_quality_score=auto_quality_score,
        speed_score=speed_score,
        stability_score=stability_score,
        score_total=score_total,
    )

    log_line(
        run_id,
        (
            f"END | model={model_name} | test={test_case.test_case_id} | prompt_id={prompt_id} | "
            f"status={status} | time={safe_round(duration)}s | "
            f"tokens={output_tokens if output_tokens is not None else ''} | "
            f"tps={safe_round(tokens_per_second)} | "
            f"quality={safe_round(auto_quality_score)} | "
            f"score={safe_round(score_total)} | "
            f"chars={len(response_text)}"
        ),
        "INFO" if status == "OK" else "ERROR",
    )

    if error_text:
        log_line(run_id, f"ERROR_DETAIL | model={model_name} | test={test_case.test_case_id} | prompt_id={prompt_id} | {error_text[:1500]}", "ERROR")

    if unload_after_each_test:
        unload_model(ollama_url, model_name)

    return result


def markdown_escape_table_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", "<br>")
    text = text.replace("|", "\\|")
    return text


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = []
    lines.append("| " + " | ".join(markdown_escape_table_cell(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(markdown_escape_table_cell(c) for c in row) + " |")
    return "\n".join(lines) + "\n"


def code_fence(text: str, language: str = "text") -> str:
    if text is None:
        text = ""
    runs = re.findall(r"`+", text)
    max_len = max((len(x) for x in runs), default=0)
    fence = "`" * max(3, max_len + 1)
    return f"{fence}{language}\n{text.rstrip()}\n{fence}\n"


def ensure_report_header() -> None:
    if AI_REPORT_PATH.exists() and AI_REPORT_PATH.stat().st_size > 0:
        return

    header = textwrap.dedent(
        f"""
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

        ## Как читать результаты

        Каждый запуск имеет уникальный `RUN_ID`.
        Каждый prompt имеет стабильный `PROMPT_ID`, рассчитанный как SHA-256 от нормализованного текста prompt.

        Внутри каждого запуска сохраняются:
        - metadata запуска
        - настройки Ollama
        - полный prompt каждого test case
        - метрики каждой модели
        - auto checks
        - полный ответ модели
        - итоговый рейтинг запуска

        ## Оценка

        `score_total` считается эвристически:

        ```text
        score_total = auto_quality_score * 0.65 + speed_score * 0.20 + stability_score * 0.15
        ```

        Это не абсолютная истина, а удобная первичная метрика.
        Финальный выбор модели лучше делать после анализа нескольких запусков.

        ---
        """
    ).lstrip()
    write_text_append(AI_REPORT_PATH, header)


def append_run_to_markdown_report(
    run_id: str,
    env_info: Dict[str, str],
    models: Sequence[str],
    test_cases: Sequence[TestCase],
    results: Sequence[ModelResult],
    args: argparse.Namespace,
    pull_results: Optional[Sequence[PullResult]] = None,
) -> None:
    ensure_report_header()

    started_at = env_info.get("datetime", now_str())

    text_parts: List[str] = []
    text_parts.append("\n\n---\n\n")
    text_parts.append(f"# RUN_ID: {run_id}\n\n")
    text_parts.append("## Run metadata\n\n")
    text_parts.append(
        markdown_table(
            ["Поле", "Значение"],
            [
                ["Дата запуска", started_at],
                ["Script version", SCRIPT_VERSION],
                ["Script path", env_info.get("script_path", "")],
                ["Work dir", env_info.get("work_dir", "")],
                ["Ollama URL", env_info.get("ollama_url", "")],
                ["Python executable", env_info.get("python_executable", "")],
                ["Python version", env_info.get("python_version", "")],
                ["Platform", env_info.get("platform", "")],
                ["Processor", env_info.get("processor", "")],
                ["Machine", env_info.get("machine", "")],
                ["Ollama version", env_info.get("ollama_version", "")],
                ["Node.js version", env_info.get("node_version", "")],
                ["npm version", env_info.get("npm_version", "")],
                ["Git version", env_info.get("git_version", "")],
                ["num_ctx", args.num_ctx],
                ["num_predict", args.num_predict],
                ["temperature", args.temperature],
                ["timeout_seconds", args.timeout],
                ["mode", "full" if args.full else "quick"],
                ["models_count", len(models)],
                ["tests_count", len(test_cases)],
                ["skip_existing_ok", not getattr(args, "rerun_existing", False)],
                ["skip_any_existing", getattr(args, "skip_any_existing", False)],
            ],
        )
    )

    text_parts.append("\n## Models in this run\n\n")
    text_parts.append(code_fence("\n".join(models), "text"))

    if pull_results is not None:
        text_parts.append("\n## Model download phase before tests\n\n")
        text_parts.append(
            markdown_table(
                ["model", "status", "attempts", "duration_sec", "error"],
                [
                    [
                        r.model_name,
                        r.status,
                        r.attempts,
                        safe_round(r.duration_seconds),
                        (r.error_text or "")[:500],
                    ]
                    for r in pull_results
                ],
            )
        )

    text_parts.append("\n## Test cases in this run\n\n")
    text_parts.append(
        markdown_table(
            ["test_case_id", "prompt_id", "title", "category"],
            [[tc.test_case_id, make_test_prompt_id(tc), tc.title, tc.category] for tc in test_cases],
        )
    )

    for test_case in test_cases:
        prompt_id = make_test_prompt_id(test_case)
        text_parts.append(f"\n## TEST_CASE: {test_case.test_case_id}\n\n")
        text_parts.append(f"**PROMPT_ID:** `{prompt_id}`\n\n")
        text_parts.append(f"**Title:** {test_case.title}\n\n")
        text_parts.append(f"**Category:** {test_case.category}\n\n")
        text_parts.append("### Prompt\n\n")
        text_parts.append(code_fence(test_case.prompt, "text"))

        test_results = [r for r in results if r.test_case_id == test_case.test_case_id]
        test_results_sorted = sorted(test_results, key=lambda r: r.score_total, reverse=True)

        text_parts.append("\n### Test summary table\n\n")
        text_parts.append(
            markdown_table(
                [
                    "model",
                    "status",
                    "score_total",
                    "quality",
                    "speed",
                    "stability",
                    "duration_sec",
                    "tokens",
                    "tokens_sec",
                    "chars",
                ],
                [
                    [
                        r.model_name,
                        r.status,
                        safe_round(r.score_total),
                        safe_round(r.auto_quality_score),
                        safe_round(r.speed_score),
                        safe_round(r.stability_score),
                        safe_round(r.duration_seconds),
                        r.output_tokens if r.output_tokens is not None else "",
                        safe_round(r.tokens_per_second),
                        r.response_chars,
                    ]
                    for r in test_results_sorted
                ],
            )
        )

        for result in test_results_sorted:
            bench_marker = {
                "run_id": result.run_id,
                "test_case_id": result.test_case_id,
                "prompt_id": result.prompt_id,
                "model_name": result.model_name,
                "status": result.status,
                "score_total": result.score_total,
                "duration_seconds": round(result.duration_seconds, 3),
            }
            text_parts.append("\n")
            text_parts.append(f"<!-- BENCH_RESULT {json.dumps(bench_marker, ensure_ascii=False, sort_keys=True)} -->\n")
            text_parts.append(f"\n### MODEL_RESULT: {result.model_name}\n\n")
            text_parts.append(
                markdown_table(
                    ["Метрика", "Значение"],
                    [
                        ["run_id", result.run_id],
                        ["test_case_id", result.test_case_id],
                        ["prompt_id", result.prompt_id],
                        ["model_name", result.model_name],
                        ["status", result.status],
                        ["http_status_code", result.http_status_code if result.http_status_code is not None else ""],
                        ["duration_seconds", safe_round(result.duration_seconds)],
                        ["duration_hms", format_seconds(result.duration_seconds)],
                        ["output_tokens", result.output_tokens if result.output_tokens is not None else ""],
                        ["tokens_per_second", safe_round(result.tokens_per_second)],
                        ["response_chars", result.response_chars],
                        ["total_duration_ns", result.total_duration_ns if result.total_duration_ns is not None else ""],
                        ["load_duration_ns", result.load_duration_ns if result.load_duration_ns is not None else ""],
                        ["prompt_eval_count", result.prompt_eval_count if result.prompt_eval_count is not None else ""],
                        ["prompt_eval_duration_ns", result.prompt_eval_duration_ns if result.prompt_eval_duration_ns is not None else ""],
                        ["eval_count", result.eval_count if result.eval_count is not None else ""],
                        ["eval_duration_ns", result.eval_duration_ns if result.eval_duration_ns is not None else ""],
                        ["auto_quality_score", safe_round(result.auto_quality_score)],
                        ["speed_score", safe_round(result.speed_score)],
                        ["stability_score", safe_round(result.stability_score)],
                        ["score_total", safe_round(result.score_total)],
                    ],
                )
            )

            text_parts.append("\n#### Auto checks\n\n")
            text_parts.append(
                markdown_table(
                    ["Проверка", "Результат", "Баллы", "Комментарий"],
                    [
                        [name, ok, safe_round(points), comment]
                        for name, ok, points, comment in result.auto_checks
                    ],
                )
            )

            if result.error_text:
                text_parts.append("\n#### Error\n\n")
                text_parts.append(code_fence(result.error_text, "text"))

            text_parts.append("\n#### Model response\n\n")
            # Для анализа ИИ лучше сохранять как text: модель может вернуть Python, SQL или PowerShell.
            text_parts.append(code_fence(result.response_text, "text"))

            text_parts.append("\n#### Human/AI notes\n\n")
            text_parts.append(
                code_fence(
                    "Заполни этот блок позже при ручной или AI-оценке. "
                    "Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.",
                    "text",
                )
            )

    text_parts.append("\n## RUN SUMMARY RANKING\n\n")
    summary = summarize_results(results)
    text_parts.append(
        markdown_table(
            [
                "rank",
                "model",
                "tests",
                "ok",
                "errors",
                "avg_score",
                "avg_quality",
                "avg_speed",
                "avg_duration_sec",
                "avg_tokens_sec",
            ],
            [
                [
                    idx + 1,
                    row["model_name"],
                    row["tests_count"],
                    row["ok_count"],
                    row["error_count"],
                    safe_round(row["avg_score"]),
                    safe_round(row["avg_quality"]),
                    safe_round(row["avg_speed"]),
                    safe_round(row["avg_duration"]),
                    safe_round(row["avg_tokens_per_second"]),
                ]
                for idx, row in enumerate(summary)
            ],
        )
    )

    text_parts.append("\n## RUN ANALYSIS PROMPT\n\n")
    analysis_prompt = textwrap.dedent(
        f"""
        Проанализируй этот RUN_ID: {run_id}.

        Нужно выбрать лучшие локальные CPU-модели для кодинга.
        Оцени:
        1. качество кода
        2. скорость
        3. стабильность
        4. выполнение инструкции
        5. пригодность для Cline/Roo Code
        6. пригодность для задач Python + FastAPI + SQLite + Node.js + PowerShell + 1C/OData

        Сделай рейтинг моделей.
        Отдельно укажи:
        - лучшую основную модель
        - лучшую быструю модель
        - модель для сложных задач
        - модели, которые лучше удалить или не использовать
        """
    ).strip()
    text_parts.append(code_fence(analysis_prompt, "text"))

    write_text_append(AI_REPORT_PATH, "".join(text_parts))


def summarize_results(results: Sequence[ModelResult]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[ModelResult]] = {}
    for result in results:
        grouped.setdefault(result.model_name, []).append(result)

    rows: List[Dict[str, Any]] = []
    for model_name, items in grouped.items():
        ok_items = [r for r in items if r.status == "OK"]
        error_items = [r for r in items if r.status != "OK"]

        def avg(values: Sequence[float]) -> Optional[float]:
            nums = [float(v) for v in values if v is not None]
            if not nums:
                return None
            return sum(nums) / len(nums)

        rows.append(
            {
                "model_name": model_name,
                "tests_count": len(items),
                "ok_count": len(ok_items),
                "error_count": len(error_items),
                "avg_score": avg([r.score_total for r in items]),
                "avg_quality": avg([r.auto_quality_score for r in items]),
                "avg_speed": avg([r.speed_score for r in items]),
                "avg_stability": avg([r.stability_score for r in items]),
                "avg_duration": avg([r.duration_seconds for r in items]),
                "avg_tokens_per_second": avg([r.tokens_per_second for r in items if r.tokens_per_second is not None]),
            }
        )

    rows.sort(
        key=lambda row: (
            row["avg_score"] if row["avg_score"] is not None else -1,
            row["ok_count"],
            -(row["avg_duration"] if row["avg_duration"] is not None else 999999),
        ),
        reverse=True,
    )
    return rows


def print_console_summary(results: Sequence[ModelResult]) -> None:
    summary = summarize_results(results)
    print("\n" + "=" * 110)
    print("ИТОГОВЫЙ РЕЙТИНГ ТЕКУЩЕГО ЗАПУСКА")
    print("=" * 110)
    print(
        f"{'№':>2} | {'Модель':35} | {'Tests':>5} | {'OK':>3} | {'Err':>3} | "
        f"{'Score':>6} | {'Quality':>7} | {'Speed':>6} | {'Avg sec':>8} | {'Tok/s':>7}"
    )
    print("-" * 110)
    for idx, row in enumerate(summary, start=1):
        print(
            f"{idx:>2} | {row['model_name'][:35]:35} | "
            f"{row['tests_count']:>5} | {row['ok_count']:>3} | {row['error_count']:>3} | "
            f"{safe_round(row['avg_score']):>6} | {safe_round(row['avg_quality']):>7} | "
            f"{safe_round(row['avg_speed']):>6} | {safe_round(row['avg_duration']):>8} | "
            f"{safe_round(row['avg_tokens_per_second']):>7}"
        )
    print("=" * 110)


def select_test_cases(all_tests: Sequence[TestCase], args: argparse.Namespace) -> List[TestCase]:
    if args.test:
        requested = set(args.test)
        selected = [tc for tc in all_tests if tc.test_case_id in requested]
        missing = sorted(requested - {tc.test_case_id for tc in selected})
        if missing:
            raise ValueError(f"Не найдены test_case_id: {', '.join(missing)}")
        return selected

    if args.full:
        return list(all_tests)

    # Если пользователь передал разовые prompt-файлы и не указал --full/--test,
    # запускаем именно эти custom prompts, а не стандартный quick-тест.
    if args.prompt_file:
        custom_tests = [tc for tc in all_tests if tc.category == "custom"]
        if custom_tests:
            return custom_tests

    # quick mode по умолчанию: один самый важный тест, чтобы CPU не гонять часами.
    return [tc for tc in all_tests if tc.test_case_id == "fastapi_sqlite_node_health"]


def select_models(all_models: Sequence[str], args: argparse.Namespace) -> List[str]:
    models = list(all_models)

    if args.model:
        requested = args.model
        selected = []
        for req in requested:
            if req in all_models:
                selected.append(req)
                continue
            matches = [m for m in all_models if req.lower() in m.lower()]
            selected.extend(matches)

        # unique preserve order
        seen = set()
        unique = []
        for m in selected:
            if m not in seen:
                unique.append(m)
                seen.add(m)

        if not unique:
            raise ValueError(f"По фильтру --model не найдено моделей: {requested}")
        models = unique

    if args.exclude_model:
        excludes = [x.lower() for x in args.exclude_model]
        models = [m for m in models if not any(ex in m.lower() for ex in excludes)]

    if args.limit_models is not None:
        models = models[: args.limit_models]

    return models


def print_prompts(test_cases: Sequence[TestCase]) -> None:
    print("\n" + "=" * 90)
    print("PROMPTS, КОТОРЫЕ БУДУТ ОТПРАВЛЕНЫ МОДЕЛЯМ")
    print("=" * 90)
    for tc in test_cases:
        print(f"\n--- TEST_CASE: {tc.test_case_id} | PROMPT_ID: {make_test_prompt_id(tc)} | {tc.title} ---\n")
        print(tc.prompt)
        print("\n" + "-" * 90)


def load_custom_prompt_tests(args: argparse.Namespace) -> List[TestCase]:
    tests: List[TestCase] = []
    for raw_path in args.prompt_file or []:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        prompt = path.read_text(encoding="utf-8", errors="replace").strip()
        if not prompt:
            raise ValueError(f"Prompt file is empty: {path}")
        prompt_id = make_prompt_id(prompt)
        tests.append(
            TestCase(
                test_case_id=f"custom_{prompt_id.lower().replace('-', '_')}",
                title=f"Custom prompt file: {path.name}",
                category="custom",
                prompt=prompt,
                expected_keywords=(),
            )
        )
    return tests


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ollama CPU coding benchmark with AI-readable Markdown report.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help=f"Ollama URL. Default: {DEFAULT_OLLAMA_URL}")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help=f"Timeout per model/test in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}")
    parser.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX, help=f"Ollama num_ctx. Default: {DEFAULT_NUM_CTX}")
    parser.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT, help=f"Ollama num_predict. Default: {DEFAULT_NUM_PREDICT}")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help=f"Ollama temperature. Default: {DEFAULT_TEMPERATURE}")

    parser.add_argument("--full", action="store_true", help="Run all test cases. Default runs only quick FastAPI test.")
    parser.add_argument("--test", action="append", help="Run only selected test_case_id. Can be used multiple times.")
    parser.add_argument("--prompt-file", action="append", help="Add one-off custom prompt from a UTF-8 text file. Can be used multiple times.")
    parser.add_argument("--model", action="append", help="Run only selected model name or partial name. Can be used multiple times.")
    parser.add_argument("--exclude-model", action="append", help="Exclude models by partial name. Can be used multiple times.")
    parser.add_argument("--limit-models", type=int, default=None, help="Limit number of models from selected list.")
    parser.add_argument("--list-models", action="store_true", help="List Ollama models and exit.")
    parser.add_argument("--list-tests", action="store_true", help="List test cases and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Show selected prompts/models, do not call Ollama.")
    parser.add_argument("--no-pull", action="store_true", help="Do not run ollama pull before tests. Default: pull selected/candidate models first.")
    parser.add_argument("--pull-retries", type=int, default=DEFAULT_PULL_RETRIES, help=f"Retries for ollama pull per model. Default: {DEFAULT_PULL_RETRIES}")
    parser.add_argument("--pull-set", choices=sorted(PULL_MODEL_SETS.keys()), default=DEFAULT_PULL_SET, help=f"Model set to pull/test when --model is not specified. Default: {DEFAULT_PULL_SET}")
    parser.add_argument("--pull-model", action="append", help="Additional exact model name to pull before tests. Can be used multiple times.")
    parser.add_argument("--test-all-installed", action="store_true", help="After pull, test all installed models instead of only pulled/selected models.")
    parser.add_argument("--rerun-existing", action="store_true", help="Run model+PROMPT_ID again even if an OK result already exists in Markdown report.")
    parser.add_argument("--skip-any-existing", action="store_true", help="Skip model+PROMPT_ID if any previous result exists, including ERROR/TIMEOUT.")
    parser.add_argument("--no-unload", action="store_true", help="Do not unload model after each test.")
    parser.add_argument("--no-pause", action="store_true", help="Do not wait for Enter at the end.")
    parser.add_argument("--hide-prompts", action="store_true", help="Do not print full prompts to console before run.")

    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    run_id = make_run_id()
    ollama_url = args.ollama_url.rstrip("/")

    all_tests = build_test_cases()
    try:
        all_tests.extend(load_custom_prompt_tests(args))
    except Exception as exc:
        print(f"ОШИБКА загрузки custom prompt: {exc}")
        return 1

    if args.list_tests:
        print("Доступные test cases:\n")
        for tc in all_tests:
            print(f"- {tc.test_case_id} | {make_test_prompt_id(tc)} | {tc.title} | category={tc.category}")
        return 0

    print("\n" + "=" * 90)
    print("OLLAMA CPU CODING BENCHMARK")
    print("=" * 90)
    print(f"RUN_ID: {run_id}")
    print(f"Script version: {SCRIPT_VERSION}")
    print(f"Technical log: {LOG_PATH}")
    print(f"AI report:     {AI_REPORT_PATH}")
    print(f"Ollama URL:    {ollama_url}")
    print("=" * 90 + "\n")

    log_line(run_id, f"Запуск benchmark script {SCRIPT_VERSION}")
    log_line(run_id, f"Technical log path: {LOG_PATH}")
    log_line(run_id, f"AI report path: {AI_REPORT_PATH}")

    env_info = get_environment_info(ollama_url)
    for key, value in env_info.items():
        log_line(run_id, f"ENV | {key}={value}")

    if not check_ollama_server(ollama_url):
        log_line(run_id, f"Ollama server не отвечает: {ollama_url}", "ERROR")
        print("\nОШИБКА: Ollama server не отвечает.")
        print("Проверь, что Ollama запущен. Например:")
        print("  ollama serve")
        print("Или проверь:")
        print(f"  {ollama_url}/api/tags")
        return 1

    try:
        all_models = get_models(ollama_url)
    except Exception as exc:
        log_line(run_id, f"Не удалось получить список моделей Ollama: {exc}", "ERROR")
        return 1

    if args.list_models and args.no_pull:
        print("Установленные Ollama-модели:\n")
        for model in all_models:
            print(f"- {model}")
        return 0

    pull_results: List[PullResult] = []
    pull_targets: List[str] = []

    if not args.no_pull:
        pull_targets = build_pull_targets(args)
        if args.list_models:
            print("Модели, которые будут скачаны/проверены перед тестом:\n")
            for model in pull_targets:
                print(f"- {model}")
            print("\nДля списка уже установленных моделей используй: --list-models --no-pull")
            return 0

        pull_results = pull_models_before_test(
            run_id=run_id,
            model_names=pull_targets,
            retries=max(1, int(args.pull_retries)),
        )

        # После скачивания обязательно перечитываем список из Ollama.
        try:
            all_models = get_models(ollama_url)
        except Exception as exc:
            log_line(run_id, f"Не удалось получить список моделей после pull phase: {exc}", "ERROR")
            return 1
    else:
        if args.list_models:
            print("Установленные Ollama-модели:\n")
            for model in all_models:
                print(f"- {model}")
            return 0

    try:
        test_cases = select_test_cases(all_tests, args)

        # В обычном режиме v6 тестирует именно подготовленные модели, а не весь хаотичный список Ollama.
        # Если нужен старый режим, используй --test-all-installed или --no-pull.
        if not args.no_pull and not args.test_all_installed and not args.model:
            selected_args = argparse.Namespace(**vars(args))
            selected_args.model = pull_targets
            models = select_models(all_models, selected_args)
        else:
            models = select_models(all_models, args)
    except Exception as exc:
        log_line(run_id, str(exc), "ERROR")
        print(f"ОШИБКА: {exc}")
        return 1

    if not models:
        log_line(run_id, "Нет моделей для тестирования.", "ERROR")
        print("ОШИБКА: Нет моделей для тестирования.")
        return 1

    print(f"Выбрано моделей: {len(models)}")
    for model in models:
        print(f"  - {model}")

    print(f"\nВыбрано тестов: {len(test_cases)}")
    for tc in test_cases:
        prompt_id = make_test_prompt_id(tc)
        print(f"  - {tc.test_case_id}: {tc.title} | PROMPT_ID={prompt_id}")
        log_line(run_id, f"SELECTED_TEST | test={tc.test_case_id} | prompt_id={prompt_id} | title={tc.title}")

    print(
        f"\nНастройки Ollama: num_ctx={args.num_ctx}, "
        f"num_predict={args.num_predict}, temperature={args.temperature}, timeout={args.timeout}s"
    )
    print(
        f"Подготовка моделей: {'OFF (--no-pull)' if args.no_pull else 'ON'} | "
        f"pull_set={getattr(args, 'pull_set', '')} | pull_retries={getattr(args, 'pull_retries', '')}"
    )

    if not args.hide_prompts:
        print_prompts(test_cases)

    if args.dry_run:
        print("\nDRY RUN: модели не запускались.")
        return 0

    existing_index = load_existing_benchmark_index(AI_REPORT_PATH)
    log_line(run_id, f"Existing benchmark index loaded: {len(existing_index)} BENCH_RESULT markers")
    print(f"\nНайдено старых BENCH_RESULT записей в Markdown-отчёте: {len(existing_index)}")
    if args.rerun_existing:
        print("Повторные тесты НЕ будут пропускаться: включён --rerun-existing")
    elif args.skip_any_existing:
        print("Повторные тесты будут пропускаться при любом старом статусе: включён --skip-any-existing")
    else:
        print("Повторные тесты будут пропускаться, если уже есть status=OK для той же пары model + PROMPT_ID")

    results: List[ModelResult] = []
    skipped_count = 0

    total_jobs = len(models) * len(test_cases)
    job_index = 0

    for tc in test_cases:
        print("\n" + "#" * 90)
        print(f"TEST_CASE: {tc.test_case_id} | {tc.title}")
        print("#" * 90)

        for model in models:
            job_index += 1
            prompt_id = make_test_prompt_id(tc)
            print(f"\n[{job_index}/{total_jobs}] Модель: {model}")
            print(f"Тест: {tc.test_case_id}")
            print(f"PROMPT_ID: {prompt_id}")

            existing_item = None
            if not args.rerun_existing:
                existing_item = should_skip_existing_result(
                    existing_index=existing_index,
                    model_name=model,
                    prompt_id=prompt_id,
                    skip_any_existing=args.skip_any_existing,
                )

            if existing_item is not None:
                skipped_count += 1
                old_run = existing_item.get("run_id", "")
                old_status = existing_item.get("status", "")
                print(f"SKIP: уже есть результат для model + PROMPT_ID | old_run={old_run} | status={old_status}")
                log_line(
                    run_id,
                    f"SKIP_EXISTING | model={model} | test={tc.test_case_id} | prompt_id={prompt_id} | old_run={old_run} | old_status={old_status}",
                    "WARN",
                )
                continue

            print("Генерация...", flush=True)

            result = run_model_test(
                run_id=run_id,
                ollama_url=ollama_url,
                model_name=model,
                test_case=tc,
                timeout_seconds=args.timeout,
                num_ctx=args.num_ctx,
                num_predict=args.num_predict,
                temperature=args.temperature,
                unload_after_each_test=not args.no_unload,
            )
            results.append(result)
            add_result_to_existing_index(existing_index, result)

            print(
                f"Результат: {result.status} | "
                f"Время: {format_seconds(result.duration_seconds)} | "
                f"Score: {safe_round(result.score_total)} | "
                f"Quality: {safe_round(result.auto_quality_score)} | "
                f"Tok/s: {safe_round(result.tokens_per_second)} | "
                f"Chars: {result.response_chars}"
            )

    if results:
        print_console_summary(results)
    else:
        print("\nНовых тестов не запускалось: все выбранные пары model + PROMPT_ID были пропущены.")
        print("Чтобы принудительно прогнать заново, добавь параметр: --rerun-existing")
    log_line(run_id, f"Run execution finished. new_results={len(results)} skipped_existing={skipped_count}")

    try:
        append_run_to_markdown_report(
            run_id=run_id,
            env_info=env_info,
            models=models,
            test_cases=test_cases,
            results=results,
            args=args,
            pull_results=pull_results,
        )
        log_line(run_id, f"Markdown report updated: {AI_REPORT_PATH}")
    except Exception as exc:
        log_line(run_id, f"Не удалось записать Markdown report: {exc}\n{traceback.format_exc()}", "ERROR")
        print(f"\nОШИБКА записи Markdown-отчёта: {exc}")

    print("\nГотово.")
    print(f"RUN_ID: {run_id}")
    print(f"Новых результатов: {len(results)} | пропущено повторов: {skipped_count}")
    print(f"Технический лог: {LOG_PATH}")
    print(f"AI-readable отчёт: {AI_REPORT_PATH}")
    print("\nЧтобы потом проанализировать результаты, загрузи файл:")
    print(f"  {AI_REPORT_PATH.name}")
    print("в любой ИИ и попроси выбрать лучшую CPU-модель для кодинга.")

    log_line(run_id, "Benchmark finished.")

    if not args.no_pause:
        try:
            input("\nНажми Enter для выхода...")
        except EOFError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
