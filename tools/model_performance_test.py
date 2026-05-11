import requests
import time
import datetime

def get_models():
    """Автоматически получает список моделей из твоей системы"""
    try:
        r = requests.get("http://localhost:11434/api/tags")
        return [m['name'] for m in r.json()['models']]
    except:
        return []

def format_time(seconds):
    """Преобразует секунды в ЧЧ:ММ:СС"""
    return str(datetime.timedelta(seconds=round(seconds)))

def benchmark():
    models = get_models()
    # Тестовое задание: генерация реального инструмента для твоего ТЗ
    prompt = "Напиши Python класс для OData 1С: метод GET для получения списка контрагентов."
    
    results = []
    
    print(f"--- ЗАПУСК ТЕСТА: {len(models)} МОДЕЛЕЙ ---")
    print(f"Время старта: {datetime.datetime.now().strftime('%H:%M:%S')}\n")
    
    for model in models:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Модель {model:25} | Генерирует код...", end=" ", flush=True)
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        start_time = time.perf_counter()
        try:
            response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=300)
            end_time = time.perf_counter()
            
            if response.status_code == 200:
                duration = end_time - start_time
                formatted = format_time(duration)
                results.append((model, duration, formatted))
                print(f"ОТРАБОТАЛА ЗА: {formatted}")
            else:
                print(f"ОШИБКА (Код: {response.status_code})")
        except Exception as e:
            print(f"ПРЕРВАНО: {e}")

    # Итоговый лог
    print("\n" + "="*55)
    print(f"{'МОДЕЛЬ':25} | {'ВРЕМЯ ВЫПОЛНЕНИЯ (ЧЧ:ММ:СС)':>25}")
    print("-" * 55)
    
    # Сортируем от самых быстрых к медленным
    results.sort(key=lambda x: x[1])
    
    for name, sec, formatted in results:
        print(f"{name:25} | {formatted:>25}")
    print("="*55)

if __name__ == "__main__":
    benchmark()