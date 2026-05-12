#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
model_agent_test_v11.py

Agent benchmark for local Ollama models.

Goal:
- test whether locally installed Ollama models can act as coding agents
- collect facts only, without automatic model scoring
- save full transcript, command outputs, final diff, and workspace facts

Recommended run from repository root:
    py .\tools\model_agent_test_v11.py --list-agent-tests
    py .\tools\model_agent_test_v11.py --agent-test agent_bugfix_file_edit --model qwen2.5-coder:3b
    py .\tools\model_agent_test_v11.py --agent-full
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCRIPT_VERSION = "v11.0"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_NUM_CTX = 4096
DEFAULT_NUM_PREDICT = 1000
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_KEEP_ALIVE = "0s"
DEFAULT_MAX_AGENT_STEPS = 20
DEFAULT_JSON_REPAIR_ATTEMPTS = 1
DEFAULT_MAX_FILE_KB = 200
DEFAULT_MAX_COMMAND_OUTPUT_CHARS = 16000

LOG_FILENAME = "model_agent_test.log"
REPORT_FILENAME = "model_agent_ai_report.md"
RUNS_DIRNAME = "agent_runs"

REQUEST_STATUSES = {"OK", "HTTP_ERROR", "TIMEOUT", "ERROR", "SKIPPED"}
AGENT_STATUSES = {
    "FINISHED",
    "MAX_STEPS_REACHED",
    "INVALID_JSON",
    "TOOL_ERROR",
    "COMMAND_BLOCKED",
    "MODEL_TIMEOUT",
    "MODEL_ERROR",
}
FINAL_CHECK_STATUSES = {"PASS", "FAIL", "NOT_RUN"}

HIDDEN_PATH_PARTS = {".venv", "__pycache__", ".pytest_cache"}
BLOCKED_COMMAND_PATTERNS = [
    r"\bdel\b",
    r"\berase\b",
    r"\brmdir\b",
    r"\bremove-item\b",
    r"\bformat\b",
    r"\bshutdown\b",
    r"\brestart-computer\b",
    r"\btaskkill\b",
    r"\breg\s+delete\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\binvoke-webrequest\b",
    r"\binvoke-restmethod\b",
    r"\bssh\b",
    r"\bscp\b",
    r"\bftp\b",
]
ALLOWED_FIRST_TOKENS = {
    "python",
    "py",
    "pytest",
    "pip",
    "dir",
    "type",
    "get-childitem",
    "get-content",
    "select-string",
    "powershell",
}


def ensure_requests() -> None:
    if importlib.util.find_spec("requests") is not None:
        return
    print("[SETUP] Python module 'requests' не найден. Пробую установить автоматически...")
    try:
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False)
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=False)
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
    except Exception as exc:  # pragma: no cover - defensive bootstrap
        print(f"[ERROR] Не удалось установить requests: {exc}")
        print(f"Выполни вручную: {sys.executable} -m pip install requests")
        raise


ensure_requests()
import requests  # noqa: E402  # pylint: disable=wrong-import-position


@dataclass(frozen=True)
class AgentTestCase:
    agent_test_id: str
    title: str
    prompt: str
    files: Dict[str, str]
    final_checks: List[str]
    protected_paths: Tuple[str, ...] = ()
    required_changed_paths: Tuple[str, ...] = ()
    required_exists_paths: Tuple[str, ...] = ()

    @property
    def prompt_id(self) -> str:
        return compute_prompt_id(self.prompt)


@dataclass
class TranscriptEntry:
    step: int
    timestamp: str
    type: str
    payload: Dict[str, Any]


@dataclass
class FinalCommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float


@dataclass
class AgentRunResult:
    run_id: str
    model_name: str
    agent_test_id: str
    prompt_id: str
    config_id: str
    agent_run_key: str
    request_status: str
    agent_status: str
    final_check_status: str
    workspace_path: str
    transcript_path: str
    diff_path: str
    duration_sec: float
    agent_steps_count: int
    tool_calls_count: int
    read_file_count: int
    write_file_count: int
    run_command_count: int
    files_changed: List[str] = field(default_factory=list)
    final_check_exit_code: Optional[int] = None
    final_check_stdout: str = ""
    final_check_stderr: str = ""
    finish_summary: str = ""
    error_text: str = ""
    max_steps_reached: bool = False
    transcript_entries: List[TranscriptEntry] = field(default_factory=list)
    final_commands: List[FinalCommandResult] = field(default_factory=list)
    raw_model_responses: List[str] = field(default_factory=list)


def now_ts() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_id() -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = hashlib.sha256(f"{time.time_ns()}-{os.getpid()}".encode("utf-8")).hexdigest()[:8].upper()
    return f"RUN-{stamp}-{suffix}"


def normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().replace("\r\n", "\n").replace("\r", "\n").splitlines())


def compute_prompt_id(text: str) -> str:
    digest = hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:16].upper()
    return f"PROMPT-{digest}"


def compute_config_id(config: Dict[str, Any]) -> str:
    encoded = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16].upper()
    return f"CONFIG-{digest}"


def make_agent_run_key(model_name: str, agent_test_id: str, prompt_id: str, config_id: str) -> str:
    return f"{model_name}||{agent_test_id}||{prompt_id}||{config_id}"


def short_text(text: str, limit: int = 300) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def safe_model_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._") or "model"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def ensure_report_header(report_path: Path) -> None:
    if report_path.exists():
        return
    header = textwrap.dedent(
        """
        # Ollama Agent Capability Report

        Append-only factual report for local Ollama coding-agent runs.
        This file intentionally does not contain automatic model scoring.
        """
    ).strip() + "\n"
    write_text(report_path, header)


def fence(text: str, language: str = "") -> str:
    return f"```{language}\n{text.rstrip()}\n```"


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("\n", "<br>")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def log_line(
    log_path: Path,
    run: str,
    model: str,
    agent_test_id: str,
    step: str,
    event_type: str,
    message: str,
) -> None:
    line = "\t".join([now_ts(), run, model, agent_test_id, step, event_type, message]) + "\n"
    append_text(log_path, line)


def get_ollama_models(ollama_url: str) -> List[str]:
    url = ollama_url.rstrip("/") + "/api/tags"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    models = [item["name"] for item in data.get("models", []) if item.get("name")]
    return sorted(dict.fromkeys(models))


def ollama_version_text() -> str:
    try:
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=20, check=False)
        return short_text(result.stdout.strip() or result.stderr.strip() or "unknown", 200)
    except Exception:
        return "unknown"


def parse_existing_run_keys(report_path: Path) -> set[str]:
    if not report_path.exists():
        return set()
    text = report_path.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"<!--\s*AGENT_RUN_KEY:\s*(.*?)\s*-->", text))


def append_transcript_entry(path: Path, entry: TranscriptEntry) -> None:
    payload = {
        "step": entry.step,
        "timestamp": entry.timestamp,
        "type": entry.type,
        **entry.payload,
    }
    append_text(path, json.dumps(payload, ensure_ascii=False) + "\n")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_hidden_relative(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    return any(part in HIDDEN_PATH_PARTS for part in parts)


def iter_visible_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if is_hidden_relative(rel):
            continue
        yield path


def collect_file_hashes(root: Path) -> Dict[str, str]:
    items: Dict[str, str] = {}
    for path in iter_visible_files(root):
        rel = path.relative_to(root).as_posix()
        items[rel] = file_sha256(path)
    return items


def compute_changed_files(initial_root: Path, final_root: Path) -> List[str]:
    initial_hashes = collect_file_hashes(initial_root)
    final_hashes = collect_file_hashes(final_root)
    changed = set()
    for rel in set(initial_hashes) | set(final_hashes):
        if initial_hashes.get(rel) != final_hashes.get(rel):
            changed.add(rel)
    return sorted(changed)


def build_unified_diff(initial_root: Path, final_root: Path) -> str:
    initial_hashes = collect_file_hashes(initial_root)
    final_hashes = collect_file_hashes(final_root)
    all_paths = sorted(set(initial_hashes) | set(final_hashes))
    chunks: List[str] = []
    for rel in all_paths:
        initial_path = initial_root / rel
        final_path = final_root / rel
        if initial_hashes.get(rel) == final_hashes.get(rel):
            continue
        before_lines = []
        after_lines = []
        if initial_path.exists():
            before_lines = initial_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        if final_path.exists():
            after_lines = final_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"initial/{rel}",
            tofile=f"workspace/{rel}",
            lineterm="",
        )
        diff_lines = list(diff)
        if diff_lines:
            chunks.append("\n".join(diff_lines))
    return "\n\n".join(chunks).strip() + ("\n" if chunks else "")


def resolve_workspace_path(workspace: Path, user_path: str) -> Path:
    path_text = (user_path or ".").strip()
    if not path_text:
        path_text = "."
    candidate = (workspace / path_text).resolve()
    workspace_resolved = workspace.resolve()
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError as exc:
        raise ValueError("path escapes workspace") from exc
    rel_parts = candidate.relative_to(workspace_resolved).parts
    if any(part in HIDDEN_PATH_PARTS for part in rel_parts):
        raise ValueError("path is inside hidden/internal directory")
    return candidate


def visible_list_dir(path: Path, workspace: Path) -> List[Dict[str, Any]]:
    entries = []
    for child in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        rel = child.relative_to(workspace).as_posix()
        if is_hidden_relative(rel):
            continue
        entries.append(
            {
                "name": child.name,
                "path": rel if rel != "." else child.name,
                "type": "dir" if child.is_dir() else "file",
                "size": None if child.is_dir() else child.stat().st_size,
            }
        )
    return entries


def summarize_tool_result(result: Dict[str, Any], limit: int = 6000) -> Dict[str, Any]:
    copied = json.loads(json.dumps(result, ensure_ascii=False))
    for field_name in ("content", "stdout", "stderr"):
        value = copied.get(field_name)
        if isinstance(value, str) and len(value) > limit:
            copied[field_name] = value[:limit] + "\n...[TRUNCATED]..."
    return copied


def json_extract_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise json.JSONDecodeError("No JSON object found", cleaned, 0)


def choose_python_command() -> List[str]:
    if os.name == "nt":
        return [sys.executable]
    return [sys.executable]


def create_workspace(base_dir: Path, files: Dict[str, str]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        path = base_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")


def bootstrap_workspace_venv(
    workspace: Path,
    command_logs_dir: Path,
    log_path: Path,
    run: str,
    model: str,
    agent_test_id: str,
) -> Tuple[Optional[Path], str]:
    requirements = workspace / "requirements.txt"
    if not requirements.exists():
        return None, "requirements.txt not found; venv bootstrap skipped"

    venv_dir = workspace / ".venv"
    venv_python = venv_dir / "Scripts" / "python.exe"
    log_file = command_logs_dir / "bootstrap_requirements.log"

    create_cmd = choose_python_command() + ["-m", "venv", str(venv_dir)]
    pip_cmd = [str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)]

    log_line(log_path, run, model, agent_test_id, "0", "COMMAND_RUN", "bootstrap: python -m venv .venv")
    create_result = subprocess.run(
        create_cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    append_text(
        log_file,
        "\n".join(
            [
                "[bootstrap] python -m venv .venv",
                f"exit_code={create_result.returncode}",
                "--- stdout ---",
                create_result.stdout,
                "--- stderr ---",
                create_result.stderr,
                "",
            ]
        ),
    )
    if create_result.returncode != 0 or not venv_python.exists():
        return None, "failed to create workspace venv"

    log_line(log_path, run, model, agent_test_id, "0", "COMMAND_RUN", "bootstrap: pip install -r requirements.txt")
    pip_result = subprocess.run(
        pip_cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    append_text(
        log_file,
        "\n".join(
            [
                "[bootstrap] pip install -r requirements.txt",
                f"exit_code={pip_result.returncode}",
                "--- stdout ---",
                pip_result.stdout,
                "--- stderr ---",
                pip_result.stderr,
                "",
            ]
        ),
    )
    if pip_result.returncode != 0:
        return None, "failed to install workspace requirements"
    return venv_python, "workspace venv ready"


def command_environment(workspace: Path, venv_python: Optional[Path]) -> Dict[str, str]:
    env = os.environ.copy()
    if venv_python and venv_python.exists():
        scripts_dir = str(venv_python.parent)
        env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = str(venv_python.parent.parent)
    env["PYTHONUTF8"] = "1"
    return env


def validate_command(command: str) -> Tuple[bool, str]:
    text = command.strip()
    if not text:
        return False, "empty command"

    lowered = text.lower()
    for pattern in BLOCKED_COMMAND_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"blocked by policy: {pattern}"

    if ".." in text:
        return False, "command contains '..'"
    if re.search(r"(?i)\b[a-z]:\\", text):
        return False, "absolute Windows paths are blocked"
    if re.search(r"(^|[\s'\"=])/+", text):
        return False, "absolute paths are blocked"

    token = re.split(r"\s+", lowered, maxsplit=1)[0]
    if token not in ALLOWED_FIRST_TOKENS:
        return False, f"command not in allowlist: {token}"

    if token == "powershell" and "-noprofile" not in lowered:
        return False, "powershell command must include -NoProfile"

    if "pip install" in lowered or "-m pip install" in lowered:
        return False, "pip install from model is blocked"

    return True, "ok"


def run_workspace_command(
    workspace: Path,
    venv_python: Optional[Path],
    command: str,
    timeout_seconds: int,
    command_logs_dir: Path,
    step: int,
) -> Dict[str, Any]:
    allowed, reason = validate_command(command)
    if not allowed:
        return {
            "ok": False,
            "blocked": True,
            "error": reason,
        }

    started = time.perf_counter()
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=command_environment(workspace, venv_python),
        check=False,
    )
    duration = time.perf_counter() - started

    log_file = command_logs_dir / f"step_{step:03d}.log"
    append_text(
        log_file,
        "\n".join(
            [
                f"command={command}",
                f"exit_code={result.returncode}",
                f"duration_sec={duration:.3f}",
                "--- stdout ---",
                result.stdout,
                "--- stderr ---",
                result.stderr,
                "",
            ]
        ),
    )

    return {
        "ok": True,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_sec": round(duration, 3),
    }


def build_agent_prompt(
    test_case: AgentTestCase,
    step: int,
    max_steps: int,
    history: List[Dict[str, Any]],
) -> str:
    tools_schema = {
        "list_dir": {"path": "."},
        "read_file": {"path": "app.py"},
        "write_file": {"path": "app.py", "content": "..."},
        "append_file": {"path": "notes.txt", "content": "..."},
        "run_command": {"command": "python -m pytest -q", "timeout_seconds": 60},
        "finish": {"summary": "Task completed", "status": "done"},
    }
    history_text = json.dumps(history, ensure_ascii=False, indent=2)
    return textwrap.dedent(
        f"""
        Задача:
        {test_case.prompt}

        Ограничения:
        - Workspace root: .
        - Работай только через tools.
        - Не выходи за пределы workspace.
        - Не меняй тесты, если это запрещено задачей.
        - Используй только один tool за шаг.
        - Сначала читай файлы, потом меняй.
        - После изменений запускай проверки.
        - Когда задача выполнена, вызови finish.

        Текущий шаг: {step} из {max_steps}
        Доступные tools:
        {json.dumps(tools_schema, ensure_ascii=False, indent=2)}

        История шага и результатов:
        {history_text}

        Верни только один JSON-объект формата:
        {{
          "thought_summary": "...",
          "tool": "read_file",
          "args": {{"path": "app.py"}}
        }}
        """
    ).strip()


def call_ollama_json(
    ollama_url: str,
    model: str,
    prompt: str,
    config: Dict[str, Any],
    timeout_seconds: int,
) -> Tuple[str, Dict[str, Any], float]:
    payload = {
        "model": model,
        "prompt": prompt,
        "system": textwrap.dedent(
            """
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
            """
        ).strip(),
        "stream": False,
        "keep_alive": config["keep_alive"],
        "options": {
            "num_ctx": config["num_ctx"],
            "num_predict": config["num_predict"],
            "temperature": config["temperature"],
        },
    }

    started = time.perf_counter()
    response = requests.post(
        ollama_url.rstrip("/") + "/api/generate",
        json=payload,
        timeout=timeout_seconds,
    )
    duration = time.perf_counter() - started
    response.raise_for_status()
    data = response.json()
    return data.get("response", ""), data, duration


def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    workspace: Path,
    venv_python: Optional[Path],
    command_logs_dir: Path,
    step: int,
    max_file_bytes: int,
) -> Dict[str, Any]:
    if tool_name == "list_dir":
        target = resolve_workspace_path(workspace, args.get("path", "."))
        if not target.exists():
            return {"ok": False, "error": "path does not exist"}
        if not target.is_dir():
            return {"ok": False, "error": "path is not a directory"}
        return {"ok": True, "entries": visible_list_dir(target, workspace)}

    if tool_name == "read_file":
        target = resolve_workspace_path(workspace, args.get("path", ""))
        if not target.exists():
            return {"ok": False, "error": "file does not exist"}
        if not target.is_file():
            return {"ok": False, "error": "path is not a file"}
        size = target.stat().st_size
        if size > max_file_bytes:
            return {"ok": False, "error": f"file too large: {size} bytes"}
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "content": content, "chars": len(content)}

    if tool_name == "write_file":
        target = resolve_workspace_path(workspace, args.get("path", ""))
        content = args.get("content", "")
        if not isinstance(content, str):
            return {"ok": False, "error": "content must be a string"}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "bytes_written": len(content.encode("utf-8"))}

    if tool_name == "append_file":
        target = resolve_workspace_path(workspace, args.get("path", ""))
        content = args.get("content", "")
        if not isinstance(content, str):
            return {"ok": False, "error": "content must be a string"}
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return {"ok": True, "bytes_appended": len(content.encode("utf-8"))}

    if tool_name == "run_command":
        command = str(args.get("command", "")).strip()
        timeout_value = int(args.get("timeout_seconds", 60))
        return run_workspace_command(
            workspace=workspace,
            venv_python=venv_python,
            command=command,
            timeout_seconds=timeout_value,
            command_logs_dir=command_logs_dir,
            step=step,
        )

    if tool_name == "finish":
        return {
            "ok": True,
            "summary": str(args.get("summary", "")),
            "status": str(args.get("status", "")),
        }

    return {"ok": False, "error": f"unknown tool: {tool_name}"}


def run_final_checks(
    test_case: AgentTestCase,
    workspace: Path,
    venv_python: Optional[Path],
    command_logs_dir: Path,
) -> List[FinalCommandResult]:
    results: List[FinalCommandResult] = []
    for index, command in enumerate(test_case.final_checks, 1):
        started = time.perf_counter()
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=300,
            env=command_environment(workspace, venv_python),
            check=False,
        )
        duration = time.perf_counter() - started
        append_text(
            command_logs_dir / f"final_check_{index:02d}.log",
            "\n".join(
                [
                    f"command={command}",
                    f"exit_code={result.returncode}",
                    f"duration_sec={duration:.3f}",
                    "--- stdout ---",
                    result.stdout,
                    "--- stderr ---",
                    result.stderr,
                    "",
                ]
            ),
        )
        results.append(
            FinalCommandResult(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_sec=duration,
            )
        )
    return results


def validate_test_case_outcome(
    test_case: AgentTestCase,
    initial_root: Path,
    workspace: Path,
    changed_files: List[str],
    final_commands: List[FinalCommandResult],
) -> Tuple[str, int, str, str]:
    combined_stdout = "\n\n".join(
        f"$ {item.command}\n{item.stdout}".rstrip() for item in final_commands
    ).strip()
    combined_stderr = "\n\n".join(
        f"$ {item.command}\n{item.stderr}".rstrip() for item in final_commands if item.stderr.strip()
    ).strip()
    if final_commands:
        overall_exit = next((item.exit_code for item in final_commands if item.exit_code != 0), final_commands[-1].exit_code)
    else:
        return "NOT_RUN", -1, "", "final checks were not executed"

    if overall_exit != 0:
        return "FAIL", overall_exit, combined_stdout, combined_stderr

    changed_set = set(changed_files)
    initial_hashes = collect_file_hashes(initial_root)
    final_hashes = collect_file_hashes(workspace)

    for rel in test_case.required_changed_paths:
        if rel not in changed_set:
            combined_stderr = (combined_stderr + f"\nrequired changed file missing: {rel}").strip()
            return "FAIL", overall_exit, combined_stdout, combined_stderr

    for rel in test_case.required_exists_paths:
        if not (workspace / rel).exists():
            combined_stderr = (combined_stderr + f"\nrequired file missing: {rel}").strip()
            return "FAIL", overall_exit, combined_stdout, combined_stderr

    for rel in test_case.protected_paths:
        if initial_hashes.get(rel) != final_hashes.get(rel):
            combined_stderr = (combined_stderr + f"\nprotected file was changed: {rel}").strip()
            return "FAIL", overall_exit, combined_stdout, combined_stderr

    return "PASS", overall_exit, combined_stdout, combined_stderr


def render_transcript(entries: List[TranscriptEntry]) -> str:
    lines = []
    for entry in entries:
        payload = {
            "step": entry.step,
            "timestamp": entry.timestamp,
            "type": entry.type,
            **entry.payload,
        }
        lines.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines)


def render_result_markdown(result: AgentRunResult) -> str:
    rows = [
        ["run_id", result.run_id],
        ["model", result.model_name],
        ["agent_test_id", result.agent_test_id],
        ["prompt_id", result.prompt_id],
        ["config_id", result.config_id],
        ["request_status", result.request_status],
        ["agent_status", result.agent_status],
        ["final_check_status", result.final_check_status],
        ["workspace path", result.workspace_path],
        ["transcript path", result.transcript_path],
        ["diff path", result.diff_path],
        ["duration_sec", f"{result.duration_sec:.2f}"],
        ["agent_steps_count", result.agent_steps_count],
        ["tool_calls_count", result.tool_calls_count],
        ["read_file_count", result.read_file_count],
        ["write_file_count", result.write_file_count],
        ["run_command_count", result.run_command_count],
        ["files_changed", ", ".join(result.files_changed) if result.files_changed else "(none)"],
        ["final_check_exit_code", result.final_check_exit_code if result.final_check_exit_code is not None else ""],
        ["max_steps_reached", str(result.max_steps_reached).lower()],
        ["finish_summary", result.finish_summary],
        ["error_text", result.error_text],
    ]

    final_command_text = "\n\n".join(
        [
            f"$ {item.command}\nexit_code={item.exit_code}\nduration_sec={item.duration_sec:.3f}\n"
            f"--- stdout ---\n{item.stdout}\n--- stderr ---\n{item.stderr}"
            for item in result.final_commands
        ]
    ).strip()

    transcript_text = render_transcript(result.transcript_entries)
    diff_text = Path(result.diff_path).read_text(encoding="utf-8", errors="replace") if Path(result.diff_path).exists() else ""

    parts = []
    parts.append(f"\n\n## AGENT_TEST_RESULT: {result.model_name} / {result.agent_test_id}\n\n")
    parts.append(f"<!-- AGENT_RUN_KEY: {result.agent_run_key} -->\n\n")
    parts.append(md_table(["Поле", "Значение"], rows))
    parts.append("\n### Final command result\n\n")
    parts.append(fence(final_command_text or "(empty)", "text"))
    parts.append("\n\n### Changed files\n\n")
    parts.append(fence("\n".join(result.files_changed) if result.files_changed else "(none)", "text"))
    parts.append("\n\n### Final diff\n\n")
    parts.append(fence(diff_text or "(empty)", "diff"))
    parts.append("\n\n### Agent transcript\n\n")
    parts.append(fence(transcript_text or "(empty)", "jsonl"))
    return "".join(parts)


def print_agent_tests(test_cases: Sequence[AgentTestCase]) -> None:
    print("Built-in agent tests:")
    for case in test_cases:
        print(f"- {case.agent_test_id}")
        print(f"  title: {case.title}")
        print(f"  prompt_id: {case.prompt_id}")


def select_agent_tests(args: argparse.Namespace, all_tests: Sequence[AgentTestCase]) -> List[AgentTestCase]:
    if args.agent_test:
        selected = []
        mapping = {case.agent_test_id: case for case in all_tests}
        for test_id in args.agent_test:
            if test_id not in mapping:
                raise SystemExit(f"Unknown agent test: {test_id}. Use --list-agent-tests.")
            selected.append(mapping[test_id])
        return selected
    if args.agent_full:
        return list(all_tests)
    return [all_tests[0]]


def select_models(args: argparse.Namespace) -> List[str]:
    if args.model:
        return list(dict.fromkeys(args.model))
    models = get_ollama_models(args.ollama_url)
    if not models:
        raise SystemExit("В Ollama не найдено моделей. Проверь: ollama list")
    return models


def run_single_agent_case(
    run: str,
    model_name: str,
    test_case: AgentTestCase,
    config: Dict[str, Any],
    config_id: str,
    args: argparse.Namespace,
    work_dir: Path,
    log_path: Path,
) -> AgentRunResult:
    started = time.perf_counter()
    request_status = "OK"
    agent_status = "MODEL_ERROR"
    final_check_status = "NOT_RUN"
    finish_summary = ""
    error_text = ""

    run_key = make_agent_run_key(model_name, test_case.agent_test_id, test_case.prompt_id, config_id)
    run_dir = work_dir / args.runs_dir / run / safe_model_name(model_name) / test_case.agent_test_id
    workspace = run_dir / "workspace"
    initial_workspace = run_dir / "workspace_initial"
    transcript_path = run_dir / "transcript.jsonl"
    diff_path = run_dir / "final_diff.patch"
    command_logs_dir = run_dir / "command_logs"
    command_logs_dir.mkdir(parents=True, exist_ok=True)

    create_workspace(workspace, test_case.files)
    create_workspace(initial_workspace, test_case.files)
    log_line(log_path, run, model_name, test_case.agent_test_id, "0", "WORKSPACE_CREATED", str(workspace))

    venv_python, bootstrap_message = bootstrap_workspace_venv(
        workspace=workspace,
        command_logs_dir=command_logs_dir,
        log_path=log_path,
        run=run,
        model=model_name,
        agent_test_id=test_case.agent_test_id,
    )
    log_line(log_path, run, model_name, test_case.agent_test_id, "0", "INFO", bootstrap_message)

    history: List[Dict[str, Any]] = []
    transcript_entries: List[TranscriptEntry] = []
    read_file_count = 0
    write_file_count = 0
    run_command_count = 0
    tool_calls_count = 0
    raw_model_responses: List[str] = []
    final_commands: List[FinalCommandResult] = []
    max_steps_reached = False

    for step in range(1, args.max_agent_steps + 1):
        log_line(log_path, run, model_name, test_case.agent_test_id, str(step), "AGENT_STEP_START", "step start")
        prompt = build_agent_prompt(test_case, step, args.max_agent_steps, history)
        model_response_text = ""
        raw_data: Dict[str, Any] = {}
        duration = 0.0
        repaired = False

        for repair_attempt in range(args.json_repair_attempts + 1):
            try:
                model_response_text, raw_data, duration = call_ollama_json(
                    ollama_url=args.ollama_url,
                    model=model_name,
                    prompt=prompt,
                    config=config,
                    timeout_seconds=args.timeout_seconds,
                )
                raw_model_responses.append(model_response_text)
                response_entry = TranscriptEntry(
                    step=step,
                    timestamp=now_ts(),
                    type="model_response",
                    payload={
                        "model": model_name,
                        "content": model_response_text,
                        "duration_sec": round(duration, 3),
                        "tokens": raw_data.get("eval_count"),
                    },
                )
                transcript_entries.append(response_entry)
                append_transcript_entry(transcript_path, response_entry)
                break
            except requests.Timeout as exc:
                request_status = "TIMEOUT"
                agent_status = "MODEL_TIMEOUT"
                error_text = str(exc)
                log_line(log_path, run, model_name, test_case.agent_test_id, str(step), "TIMEOUT", short_text(error_text, 400))
                break
            except requests.HTTPError as exc:
                request_status = "HTTP_ERROR"
                agent_status = "MODEL_ERROR"
                error_text = str(exc)
                log_line(log_path, run, model_name, test_case.agent_test_id, str(step), "ERROR", short_text(error_text, 400))
                break
            except requests.RequestException as exc:
                request_status = "ERROR"
                agent_status = "MODEL_ERROR"
                error_text = str(exc)
                log_line(log_path, run, model_name, test_case.agent_test_id, str(step), "ERROR", short_text(error_text, 400))
                break
        else:  # pragma: no cover - defensive branch
            pass

        if request_status != "OK":
            break

        try:
            model_json = json_extract_object(model_response_text)
        except json.JSONDecodeError:
            if args.json_repair_attempts > 0 and not repaired:
                repair_prompt = prompt + "\n\nТвой предыдущий ответ не был валидным JSON. Верни только один JSON-объект с tool и args."
                try:
                    model_response_text, raw_data, duration = call_ollama_json(
                        ollama_url=args.ollama_url,
                        model=model_name,
                        prompt=repair_prompt,
                        config=config,
                        timeout_seconds=args.timeout_seconds,
                    )
                    repaired = True
                    raw_model_responses.append(model_response_text)
                    response_entry = TranscriptEntry(
                        step=step,
                        timestamp=now_ts(),
                        type="model_response_repair",
                        payload={
                            "model": model_name,
                            "content": model_response_text,
                            "duration_sec": round(duration, 3),
                            "tokens": raw_data.get("eval_count"),
                        },
                    )
                    transcript_entries.append(response_entry)
                    append_transcript_entry(transcript_path, response_entry)
                    model_json = json_extract_object(model_response_text)
                except Exception as exc:  # pragma: no cover - repair path
                    request_status = "ERROR" if not isinstance(exc, requests.Timeout) else "TIMEOUT"
                    agent_status = "INVALID_JSON"
                    error_text = f"JSON repair failed: {exc}"
                    break
            else:
                agent_status = "INVALID_JSON"
                error_text = "model returned invalid JSON"
                log_line(log_path, run, model_name, test_case.agent_test_id, str(step), "ERROR", error_text)
                break

        tool_name = str(model_json.get("tool", "")).strip()
        tool_args = model_json.get("args", {})
        if not isinstance(tool_args, dict):
            tool_args = {}

        tool_calls_count += 1
        if tool_name == "read_file":
            read_file_count += 1
        elif tool_name in {"write_file", "append_file"}:
            write_file_count += 1
        elif tool_name == "run_command":
            run_command_count += 1

        log_line(log_path, run, model_name, test_case.agent_test_id, str(step), "TOOL_CALL", f"{tool_name} {short_text(json.dumps(tool_args, ensure_ascii=False), 200)}")
        try:
            tool_result = execute_tool(
                tool_name=tool_name,
                args=tool_args,
                workspace=workspace,
                venv_python=venv_python,
                command_logs_dir=command_logs_dir,
                step=step,
                max_file_bytes=args.max_file_kb * 1024,
            )
        except subprocess.TimeoutExpired as exc:
            agent_status = "TOOL_ERROR"
            error_text = f"tool timeout: {exc}"
            break
        except Exception as exc:  # pragma: no cover - defensive
            agent_status = "TOOL_ERROR"
            error_text = f"tool execution error: {exc}"
            break

        tool_entry = TranscriptEntry(
            step=step,
            timestamp=now_ts(),
            type="tool_result",
            payload={
                "tool": tool_name,
                "ok": tool_result.get("ok", False),
                "result": summarize_tool_result(tool_result, args.max_command_output_chars),
            },
        )
        transcript_entries.append(tool_entry)
        append_transcript_entry(transcript_path, tool_entry)
        log_line(
            log_path,
            run,
            model_name,
            test_case.agent_test_id,
            str(step),
            "TOOL_RESULT",
            short_text(json.dumps(summarize_tool_result(tool_result), ensure_ascii=False), 400),
        )

        if tool_name == "run_command" and tool_result.get("blocked"):
            agent_status = "COMMAND_BLOCKED"
            error_text = tool_result.get("error", "command blocked")
            break

        history.append(
            {
                "step": step,
                "thought_summary": model_json.get("thought_summary", ""),
                "tool": tool_name,
                "args": tool_args,
                "result": summarize_tool_result(tool_result, args.max_command_output_chars),
            }
        )

        if tool_name == "finish":
            finish_summary = str(tool_result.get("summary", "")).strip()
            agent_status = "FINISHED"
            log_line(log_path, run, model_name, test_case.agent_test_id, str(step), "FINISH", short_text(finish_summary, 300))
            break

        if tool_name not in {"list_dir", "read_file", "write_file", "append_file", "run_command", "finish"}:
            agent_status = "TOOL_ERROR"
            error_text = f"unknown tool requested: {tool_name}"
            break
    else:
        agent_status = "MAX_STEPS_REACHED"
        max_steps_reached = True
        log_line(log_path, run, model_name, test_case.agent_test_id, str(args.max_agent_steps), "MAX_STEPS_REACHED", "agent loop limit reached")

    log_line(log_path, run, model_name, test_case.agent_test_id, "-", "FINAL_CHECK_START", "starting final checks")
    final_commands = run_final_checks(
        test_case=test_case,
        workspace=workspace,
        venv_python=venv_python,
        command_logs_dir=command_logs_dir,
    )
    final_check_status, final_check_exit_code, final_check_stdout, final_check_stderr = validate_test_case_outcome(
        test_case=test_case,
        initial_root=initial_workspace,
        workspace=workspace,
        changed_files=compute_changed_files(initial_workspace, workspace),
        final_commands=final_commands,
    )
    log_line(
        log_path,
        run,
        model_name,
        test_case.agent_test_id,
        "-",
        "FINAL_CHECK_END",
        f"status={final_check_status} exit_code={final_check_exit_code}",
    )

    changed_files = compute_changed_files(initial_workspace, workspace)
    diff_text = build_unified_diff(initial_workspace, workspace)
    write_text(diff_path, diff_text)

    duration_sec = time.perf_counter() - started
    return AgentRunResult(
        run_id=run,
        model_name=model_name,
        agent_test_id=test_case.agent_test_id,
        prompt_id=test_case.prompt_id,
        config_id=config_id,
        agent_run_key=run_key,
        request_status=request_status,
        agent_status=agent_status,
        final_check_status=final_check_status,
        workspace_path=str(workspace.resolve()),
        transcript_path=str(transcript_path.resolve()),
        diff_path=str(diff_path.resolve()),
        duration_sec=duration_sec,
        agent_steps_count=len([e for e in transcript_entries if e.type.startswith("model_response")]),
        tool_calls_count=tool_calls_count,
        read_file_count=read_file_count,
        write_file_count=write_file_count,
        run_command_count=run_command_count,
        files_changed=changed_files,
        final_check_exit_code=final_check_exit_code,
        final_check_stdout=final_check_stdout,
        final_check_stderr=final_check_stderr,
        finish_summary=finish_summary,
        error_text=error_text,
        max_steps_reached=max_steps_reached,
        transcript_entries=transcript_entries,
        final_commands=final_commands,
        raw_model_responses=raw_model_responses,
    )


def build_agent_tests() -> List[AgentTestCase]:
    bugfix_files = {
        "app.py": textwrap.dedent(
            """
            import sqlite3

            DB_PATH = "items.db"

            def get_conn():
                conn = sqlite3.connect(DB_PATH)
                return conn.cursor()

            def list_items():
                cur = get_conn()
                rows = cur.execute("select id name from items").fetchall()
                return [{"id": row[0], "name": row[1]} for row in rows]

            def add_item(name: str):
                cur = get_conn()
                cur.execute(f"insert into items(name) values('{name}')")
                return {"ok": true}
            """
        ).strip(),
        "tests/test_app.py": textwrap.dedent(
            """
            import app

            def test_add_and_list(tmp_path):
                app.DB_PATH = str(tmp_path / "items.db")
                result = app.add_item("alpha")
                assert result == {"ok": True}
                rows = app.list_items()
                assert len(rows) == 1
                assert rows[0]["name"] == "alpha"

            def test_handles_quote_in_name(tmp_path):
                app.DB_PATH = str(tmp_path / "items.db")
                app.add_item("O'Reilly")
                rows = app.list_items()
                assert rows[0]["name"] == "O'Reilly"
            """
        ).strip(),
        "requirements.txt": "pytest>=8,<9",
    }

    health_files = {
        "main.py": textwrap.dedent(
            """
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/")
            def root():
                return {"message": "hello"}
            """
        ).strip(),
        "tests/test_health.py": textwrap.dedent(
            """
            import sys

            from fastapi.testclient import TestClient

            import main

            client = TestClient(main.app)

            def test_health_endpoint():
                response = client.get("/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert "python_version" in data
                assert data["python_version"].startswith(str(sys.version_info.major))
            """
        ).strip(),
        "requirements.txt": "\n".join(
            [
                "fastapi>=0.110,<1",
                "uvicorn>=0.29,<1",
                "httpx>=0.27,<1",
                "pytest>=8,<9",
            ]
        ),
    }

    refactor_files = {
        "app.py": textwrap.dedent(
            """
            import sqlite3

            DB_PATH = "users.db"

            def ensure_db():
                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE)"
                )
                conn.commit()
                conn.close()

            def add_user(name: str, email: str):
                ensure_db()
                conn = sqlite3.connect(DB_PATH)
                conn.execute("INSERT INTO users(name, email) VALUES(?, ?)", (name, email))
                conn.commit()
                conn.close()

            def get_usernames():
                ensure_db()
                conn = sqlite3.connect(DB_PATH)
                rows = conn.execute("SELECT name FROM users ORDER BY id").fetchall()
                conn.close()
                return [row[0] for row in rows]
            """
        ).strip(),
        "tests/test_app.py": textwrap.dedent(
            """
            import app

            def test_existing_api_still_works(tmp_path):
                app.DB_PATH = str(tmp_path / "users.db")
                app.add_user("Alice", "alice@example.com")
                app.add_user("Bob", "bob@example.com")
                assert app.get_usernames() == ["Alice", "Bob"]
            """
        ).strip(),
        "requirements.txt": "pytest>=8,<9",
    }

    rag_files = {
        "docs/doc1.txt": "RAG chunking starts with reading local files and splitting them into useful pieces.",
        "docs/doc2.md": "# Notes\n\nA minimal dataset should include chunk text, source path, and ordering metadata.",
        "tests/test_prepare_rag.py": textwrap.dedent(
            """
            import json
            import subprocess
            import sys
            from pathlib import Path

            def test_prepare_rag_dataset_script():
                root = Path(__file__).resolve().parents[1]
                result = subprocess.run(
                    [sys.executable, "prepare_rag_dataset.py"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert result.returncode == 0, result.stdout + result.stderr

                chunks_path = root / "rag_chunks.jsonl"
                manifest_path = root / "manifest.json"
                assert chunks_path.exists()
                assert manifest_path.exists()

                lines = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                assert len(lines) > 0
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                assert manifest["chunks_count"] == len(lines)
                assert manifest["documents_count"] == 2
            """
        ).strip(),
        "requirements.txt": "pytest>=8,<9",
    }

    powershell_files = {
        "main.py": textwrap.dedent(
            """
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/")
            def root():
                return {"message": "hello"}
            """
        ).strip(),
        "tests/test_runner_file.py": textwrap.dedent(
            """
            from pathlib import Path

            def test_runner_file_exists_and_mentions_check_only():
                script = Path("run_fastapi.ps1")
                assert script.exists()
                content = script.read_text(encoding="utf-8").lower()
                assert "checkonly" in content
                assert ".venv" in content
                assert "8010" in content
            """
        ).strip(),
        "requirements.txt": "\n".join(
            [
                "fastapi>=0.110,<1",
                "uvicorn>=0.29,<1",
                "pytest>=8,<9",
            ]
        ),
    }

    return [
        AgentTestCase(
            agent_test_id="agent_bugfix_file_edit",
            title="Fix file and pass tests",
            prompt="Исправь app.py. Не меняй tests/test_app.py. Запусти pytest. Добейся прохождения тестов.",
            files=bugfix_files,
            final_checks=["python -m pytest -q"],
            protected_paths=("tests/test_app.py",),
            required_changed_paths=("app.py",),
        ),
        AgentTestCase(
            agent_test_id="agent_add_fastapi_health_endpoint",
            title="Add FastAPI /health endpoint",
            prompt='Добавь GET /health. Endpoint должен вернуть {"status": "ok"} и версию Python. Запусти тесты и исправь ошибки.',
            files=health_files,
            final_checks=["python -m pytest -q"],
            protected_paths=("tests/test_health.py",),
            required_changed_paths=("main.py",),
        ),
        AgentTestCase(
            agent_test_id="agent_refactor_without_breaking_tests",
            title="Refactor single file into modules",
            prompt="Раздели app.py на db.py, models.py, main.py. Сохрани публичное поведение API. Тесты должны пройти.",
            files=refactor_files,
            final_checks=["python -m pytest -q"],
            protected_paths=("tests/test_app.py",),
            required_exists_paths=("db.py", "models.py", "main.py"),
        ),
        AgentTestCase(
            agent_test_id="agent_rag_pipeline_minimal",
            title="Create minimal RAG dataset pipeline",
            prompt="Создай prepare_rag_dataset.py. Он должен читать docs/, делать chunking и создавать rag_chunks.jsonl + manifest.json. Запусти тесты.",
            files=rag_files,
            final_checks=["python -m pytest -q"],
            protected_paths=("tests/test_prepare_rag.py",),
            required_exists_paths=("prepare_rag_dataset.py", "rag_chunks.jsonl", "manifest.json"),
        ),
        AgentTestCase(
            agent_test_id="agent_powershell_runner",
            title="Create PowerShell runner with CheckOnly mode",
            prompt="Создай run_fastapi.ps1 для Windows. Скрипт должен создать .venv, поставить зависимости и запустить main.py на порту 8010. Не запускай бесконечный сервер в тесте; добавь режим -CheckOnly.",
            files=powershell_files,
            final_checks=[
                "powershell -NoProfile -ExecutionPolicy Bypass -File .\\run_fastapi.ps1 -CheckOnly",
                "python -m pytest -q",
            ],
            protected_paths=("tests/test_runner_file.py",),
            required_exists_paths=("run_fastapi.ps1",),
        ),
    ]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Agent capability benchmark for local Ollama models. Collect facts only, no automatic scoring.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL), help="Ollama base URL")
    parser.add_argument("--model", action="append", help="Model to test. Can be used multiple times.")
    parser.add_argument("--agent-full", action="store_true", help="Run all built-in agent tests")
    parser.add_argument("--agent-test", action="append", help="Run one specific built-in agent test. Can be used multiple times.")
    parser.add_argument("--list-agent-tests", action="store_true", help="Show built-in agent tests and prompt IDs")
    parser.add_argument("--rerun-existing", action="store_true", help="Do not skip model+agent_test_id+prompt_id+config_id already present in report")
    parser.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX, help="Ollama num_ctx")
    parser.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT, help="Ollama num_predict")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Ollama temperature")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout per model step")
    parser.add_argument("--keep-alive", default=DEFAULT_KEEP_ALIVE, help="Ollama keep_alive")
    parser.add_argument("--max-agent-steps", type=int, default=DEFAULT_MAX_AGENT_STEPS, help="Maximum tool steps per agent run")
    parser.add_argument("--json-repair-attempts", type=int, default=DEFAULT_JSON_REPAIR_ATTEMPTS, help="Invalid JSON repair retries")
    parser.add_argument("--max-file-kb", type=int, default=DEFAULT_MAX_FILE_KB, help="Max readable file size for read_file tool")
    parser.add_argument("--max-command-output-chars", type=int, default=DEFAULT_MAX_COMMAND_OUTPUT_CHARS, help="Prompt-safe clip for stdout/stderr/content")
    parser.add_argument("--log-file", default=LOG_FILENAME, help="Technical log path, relative to current directory")
    parser.add_argument("--report-file", default=REPORT_FILENAME, help="Markdown report path, relative to current directory")
    parser.add_argument("--runs-dir", default=RUNS_DIRNAME, help="Directory for per-run artifacts")
    parser.add_argument("--no-pause", action="store_true", help="Do not wait for Enter at the end")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    all_tests = build_agent_tests()

    if args.list_agent_tests:
        print_agent_tests(all_tests)
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
        "max_agent_steps": args.max_agent_steps,
    }
    config_id = compute_config_id(config)

    selected_tests = select_agent_tests(args, all_tests)

    try:
        models = select_models(args)
    except Exception as exc:
        print(f"Не удалось получить список моделей: {exc}")
        if not args.no_pause:
            input("Нажми Enter для выхода...")
        return 1

    print("=" * 72)
    print("Ollama Agent Capability Benchmark")
    print("=" * 72)
    print(f"RUN_ID: {run}")
    print(f"CONFIG_ID: {config_id}")
    print(f"Ollama URL: {args.ollama_url}")
    print(f"Ollama version: {ollama_version_text()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.platform()}")
    print(f"Models: {len(models)}")
    print(f"Agent tests: {len(selected_tests)}")
    print(f"Log: {log_path}")
    print(f"Report: {report_path}")
    print("=" * 72)

    log_line(log_path, run, "-", "-", "-", "START", f"script={SCRIPT_VERSION} config_id={config_id}")
    try:
        installed = get_ollama_models(args.ollama_url)
        log_line(log_path, run, "-", "-", "-", "OLLAMA_API_OK", f"installed_models={len(installed)}")
    except Exception as exc:
        log_line(log_path, run, "-", "-", "-", "ERROR", f"OLLAMA API ERROR: {exc}")
        print(f"Не удалось подключиться к Ollama API: {exc}")
        if not args.no_pause:
            input("Нажми Enter для выхода...")
        return 1

    existing_keys = parse_existing_run_keys(report_path)
    results: List[AgentRunResult] = []

    for test_index, test_case in enumerate(selected_tests, 1):
        print("\n" + "=" * 72)
        print(f"AGENT TEST {test_index}/{len(selected_tests)}: {test_case.agent_test_id}")
        print(f"PROMPT_ID: {test_case.prompt_id}")
        print(test_case.prompt)
        print("=" * 72)

        for model_index, model_name in enumerate(models, 1):
            run_key = make_agent_run_key(model_name, test_case.agent_test_id, test_case.prompt_id, config_id)
            if not args.rerun_existing and run_key in existing_keys:
                print(f"[{model_index}/{len(models)}] SKIP: {model_name} already exists for this config")
                log_line(log_path, run, model_name, test_case.agent_test_id, "-", "SKIPPED", "existing AGENT_RUN_KEY found in report")
                continue

            print(f"[{model_index}/{len(models)}] Model: {model_name}")
            result = run_single_agent_case(
                run=run,
                model_name=model_name,
                test_case=test_case,
                config=config,
                config_id=config_id,
                args=args,
                work_dir=work_dir,
                log_path=log_path,
            )
            results.append(result)

            print(
                f"  status={result.agent_status} final={result.final_check_status} "
                f"steps={result.agent_steps_count} commands={result.run_command_count} "
                f"changed={len(result.files_changed)} duration={result.duration_sec:.1f}s"
            )

            append_text(report_path, render_result_markdown(result))

    log_line(log_path, run, "-", "-", "-", "FINISH", f"results={len(results)}")

    print("\n" + "=" * 72)
    print("ГОТОВО")
    print(f"RUN_ID: {run}")
    print(f"Results written: {len(results)}")
    print(f"Log: {log_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {(work_dir / args.runs_dir).resolve()}")
    print("=" * 72)

    if not args.no_pause:
        input("Нажми Enter для выхода...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
