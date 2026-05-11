# model_performance_test.py
# Тест производительности локальных моделей Ollama.
# Если нужные Python-модули не установлены, скрипт сам попробует их установить.

import sys
import subprocess
import importlib.util
import time
import datetime


REQUIRED_PACKAGES = [
    {
        "module": "requests",
        "package": "requests",
    }
]


def ensure_pip():
    """Проверяет наличие pip. Если pip нет — пробует установить через ensurepip."""
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    except subprocess.CalledProcessError:
        pass

    print("[SETUP] pip не найден. Пробую установить pip через ensurepip...")

    try:
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
    except Exception as e:
        print("[ERROR] Не удалось установить pip автоматически.")
        print(f"[ERROR] Причина: {e}")
        print("[ERROR] Выполни вручную:")
        print("        py -m ensurepip --upgrade")
        print("        py -m pip install --upgrade pip")
        raise


def ensure_package(module_name, package_name=None):
    """
    Проверяет наличие Python-модуля.
    Если модуль отсутствует — устанавливает соответствующий pip-пакет.
    """
    if package_name is None:
        package_name = module_name

    if importlib.util.find_spec(module_name) is not None:
        return

    ensure_pip()

    print(f"[SETUP] Модуль '{module_name}' не найден. Устанавливаю пакет '{package_name}'...")

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"[SETUP] Пакет '{package_name}' установлен.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Не удалось установить пакет '{package_name}'.")
        print(f"[ERROR] Код ошибки: {e.returncode}")
        print("[ERROR] Попробуй вручную:")
        print(f"        py -m pip install {package_name}")
        raise


def install_required_packages():
    """Устанавливает все внешние зависимости, указанные в REQUIRED_PACKAGES."""
    for item in REQUIRED_PACKAGES:
        ensure_package(item["module"], item["package"])


install_required_packages()

import requests  # noqa: E402


OLLAMA_BASE_URL = "http://localhost:11434"
GENERATE_TIMEOUT_SECONDS = 300


def get_models():
    """Автоматически получает список моделей из локального Ollama."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=15)
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        return [model["name"] for model in models if "name" in model]
    except requests.exceptions.ConnectionError:
        print("[ERROR] Ollama не отвечает на http://localhost:11434")
        print("[ERROR] Проверь, что Ollama запущен.")
        print("[ERROR] Команда проверки:")
        print("        ollama list")
        return []
    except requests.exceptions.Timeout:
        print("[ERROR] Таймаут подключения к Ollama.")
        return []
    except Exception as e:
        print(f"[ERROR] Не удалось получить список моделей Ollama: {e}")
        return []


def format_time(seconds):
    """Преобразует секунды в ЧЧ:ММ:СС."""
    return str(datetime.timedelta(seconds=round(seconds)))


def benchmark():
    models = get_models()

    if not models:
        print("[STOP] Модели Ollama не найдены.")
        print("[INFO] Проверь список моделей командой:")
        print("       ollama list")
        return

    # Тестовое задание: генерация реального инструмента для твоего ТЗ.
    prompt = "Напиши Python класс для OData 1С: метод GET для получения списка контрагентов."

    results = []

    print(f"--- ЗАПУСК ТЕСТА: {len(models)} МОДЕЛЕЙ ---")
    print(f"Время старта: {datetime.datetime.now().strftime('%H:%M:%S')}\n")

    for model in models:
        print(
            f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
            f"Модель {model:35} | Генерирует код...",
            end=" ",
            flush=True,
        )

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }

        start_time = time.perf_counter()

        try:
            response = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
                timeout=GENERATE_TIMEOUT_SECONDS,
            )

            end_time = time.perf_counter()

            if response.status_code == 200:
                duration = end_time - start_time
                formatted = format_time(duration)
                results.append((model, duration, formatted))
                print(f"ОТРАБОТАЛА ЗА: {formatted}")
            else:
                print(f"ОШИБКА HTTP {response.status_code}")
                print(f"Ответ Ollama: {response.text[:500]}")
        except requests.exceptions.Timeout:
            print(f"ПРЕРВАНО: таймаут {GENERATE_TIMEOUT_SECONDS} секунд")
        except Exception as e:
            print(f"ПРЕРВАНО: {e}")

    print_results(results)


def print_results(results):
    """Печатает итоговую таблицу."""
    print("\n" + "=" * 70)
    print(f"{'МОДЕЛЬ':35} | {'ВРЕМЯ ВЫПОЛНЕНИЯ (ЧЧ:ММ:СС)':>30}")
    print("-" * 70)

    if not results:
        print("Нет успешных результатов.")
        print("=" * 70)
        return

    # Сортируем от самых быстрых к медленным.
    results.sort(key=lambda item: item[1])

    for name, seconds, formatted in results:
        print(f"{name:35} | {formatted:>30}")

    print("=" * 70)


if __name__ == "__main__":
    benchmark()
