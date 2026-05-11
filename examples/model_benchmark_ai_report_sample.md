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


---

# RUN_ID: RUN-20260510-204751-M4XQ9GJ9

## Run metadata

| Поле | Значение |
| --- | --- |
| Дата запуска | 2026-05-10 20:47:51 |
| Script version | v7.0 |
| Script path | C:\Work\Prj_1_AI_Test\tools\model_performance_test_v7.py |
| Work dir | C:\Work\Prj_1_AI_Test\tools |
| Ollama URL | http://localhost:11434 |
| Python executable | C:\Python314\python.exe |
| Python version | 3.14.4 (tags/v3.14.4:23116f9, Apr  7 2026, 14:10:54) [MSC v.1944 64 bit (AMD64)] |
| Platform | Windows-10-10.0.19044-SP0 |
| Processor | Intel64 Family 6 Model 165 Stepping 3, GenuineIntel |
| Machine | AMD64 |
| Ollama version | ollama version is 0.23.1 |
| Node.js version | NOT INSTALLED |
| npm version | NOT INSTALLED |
| Git version | git version 2.54.0.windows.1 |
| num_ctx | 2048 |
| num_predict | 700 |
| temperature | 0.1 |
| timeout_seconds | 600 |
| mode | quick |
| models_count | 8 |
| tests_count | 1 |
| skip_existing_ok | True |
| skip_any_existing | False |

## Models in this run

```text
qwen2.5-coder:1.5b
qwen2.5-coder:3b
codegemma:2b
deepseek-coder:1.3b
starcoder2:3b
granite-code:3b
stable-code:3b
yi-coder:1.5b
```

## Model download phase before tests

| model | status | attempts | duration_sec | error |
| --- | --- | --- | --- | --- |

## Test cases in this run

| test_case_id | prompt_id | title | category |
| --- | --- | --- | --- |
| fastapi_sqlite_node_health | PROMPT-F42A416EEC074CA7 | FastAPI + SQLite + Node.js health endpoint | backend |

## TEST_CASE: fastapi_sqlite_node_health

**PROMPT_ID:** `PROMPT-F42A416EEC074CA7`

**Title:** FastAPI + SQLite + Node.js health endpoint

**Category:** backend

### Prompt

```text
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
```

### Test summary table

| model | status | score_total | quality | speed | stability | duration_sec | tokens | tokens_sec | chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen2.5-coder:1.5b | OK | 10.0 | 10.0 | 10.0 | 10.0 | 28.36 | 489 | 27.24 | 1980 |
| yi-coder:1.5b | OK | 10.0 | 10.0 | 10.0 | 10.0 | 25.66 | 351 | 22.68 | 1283 |
| deepseek-coder:1.3b | OK | 9.76 | 10.0 | 8.8 | 10.0 | 38.88 | 700 | 25.57 | 2629 |
| qwen2.5-coder:3b | OK | 9.6 | 10.0 | 8.0 | 10.0 | 50.39 | 491 | 13.85 | 1925 |
| codegemma:2b | OK | 9.6 | 10.0 | 8.0 | 10.0 | 53.35 | 700 | 16.98 | 2950 |
| granite-code:3b | OK | 9.2 | 10.0 | 6.0 | 10.0 | 79.12 | 465 | 7.92 | 1614 |
| stable-code:3b | OK | 9.2 | 10.0 | 6.0 | 10.0 | 95.54 | 700 | 9.13 | 2367 |
| starcoder2:3b | OK | 2.75 | 0.0 | 10.0 | 5.0 | 15.94 | 2 | 22.81 | 1 |

<!-- BENCH_RESULT {"duration_seconds": 28.356, "model_name": "qwen2.5-coder:1.5b", "prompt_id": "PROMPT-F42A416EEC074CA7", "run_id": "RUN-20260510-204751-M4XQ9GJ9", "score_total": 10.0, "status": "OK", "test_case_id": "fastapi_sqlite_node_health"} -->

### MODEL_RESULT: qwen2.5-coder:1.5b

| Метрика | Значение |
| --- | --- |
| run_id | RUN-20260510-204751-M4XQ9GJ9 |
| test_case_id | fastapi_sqlite_node_health |
| prompt_id | PROMPT-F42A416EEC074CA7 |
| model_name | qwen2.5-coder:1.5b |
| status | OK |
| http_status_code | 200 |
| duration_seconds | 28.36 |
| duration_hms | 0:00:28 |
| output_tokens | 489 |
| tokens_per_second | 27.24 |
| response_chars | 1980 |
| total_duration_ns | 26291448400 |
| load_duration_ns | 2314570300 |
| prompt_eval_count | 398 |
| prompt_eval_duration_ns | 4357912200 |
| eval_count | 489 |
| eval_duration_ns | 17949791000 |
| auto_quality_score | 10.0 |
| speed_score | 10.0 |
| stability_score | 10.0 |
| score_total | 10.0 |

#### Auto checks

| Проверка | Результат | Баллы | Комментарий |
| --- | --- | --- | --- |
| contains_fastapi_import | YES | 1.3 |  |
| contains_sqlite | YES | 1.2 |  |
| contains_cars_table | YES | 1.0 |  |
| contains_post_cars | YES | 1.0 |  |
| contains_get_cars | YES | 0.8 |  |
| contains_get_cars_plate | YES | 0.8 |  |
| contains_health_endpoint | YES | 1.0 |  |
| contains_node_check | YES | 1.0 |  |
| contains_pydantic_model | NO | 0.0 |  |
| contains_http_exception | YES | 0.6 |  |
| contains_uvicorn_main | YES | 0.6 |  |

#### Model response

````text
```python
from fastapi import FastAPI, HTTPException, Query
import sqlite3
import uvicorn

app = FastAPI()

# SQLite connection
def get_db():
    conn = sqlite3.connect('cars.db')
    return conn

@app.on_event("startup")
async def startup():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate TEXT UNIQUE NOT NULL,
        owner TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')
    conn.commit()

@app.post("/cars")
async def add_car(plate: str, owner: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO cars (plate, owner, created_at) VALUES (?, ?, ?)", (plate, owner, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return {"message": "Car added successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Plate already exists")

@app.get("/cars")
async def get_cars():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cars")
    cars = cursor.fetchall()
    return {"cars": [dict(row) for row in cars]}

@app.get("/cars/{plate}")
async def get_car(plate: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cars WHERE plate=?", (plate,))
    car = cursor.fetchone()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    return {"car": dict(car)}

@app.get("/health")
async def health():
    try:
        import subprocess
        node_version = subprocess.check_output(['node', '--version']).decode('utf-8').strip()
        return {"status": "ok", "python_version": sys.version, "node_installed": True}
    except subprocess.CalledProcessError:
        return {"status": "error", "python_version": sys.version, "node_installed": False}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
```
````

#### Human/AI notes

```text
Заполни этот блок позже при ручной или AI-оценке. Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.
```

<!-- BENCH_RESULT {"duration_seconds": 25.659, "model_name": "yi-coder:1.5b", "prompt_id": "PROMPT-F42A416EEC074CA7", "run_id": "RUN-20260510-204751-M4XQ9GJ9", "score_total": 10.0, "status": "OK", "test_case_id": "fastapi_sqlite_node_health"} -->

### MODEL_RESULT: yi-coder:1.5b

| Метрика | Значение |
| --- | --- |
| run_id | RUN-20260510-204751-M4XQ9GJ9 |
| test_case_id | fastapi_sqlite_node_health |
| prompt_id | PROMPT-F42A416EEC074CA7 |
| model_name | yi-coder:1.5b |
| status | OK |
| http_status_code | 200 |
| duration_seconds | 25.66 |
| duration_hms | 0:00:26 |
| output_tokens | 351 |
| tokens_per_second | 22.68 |
| response_chars | 1283 |
| total_duration_ns | 23610939100 |
| load_duration_ns | 710633200 |
| prompt_eval_count | 542 |
| prompt_eval_duration_ns | 6242825500 |
| eval_count | 351 |
| eval_duration_ns | 15477381000 |
| auto_quality_score | 10.0 |
| speed_score | 10.0 |
| stability_score | 10.0 |
| score_total | 10.0 |

#### Auto checks

| Проверка | Результат | Баллы | Комментарий |
| --- | --- | --- | --- |
| contains_fastapi_import | NO | 0.0 |  |
| contains_sqlite | YES | 1.2 |  |
| contains_cars_table | NO | 0.0 |  |
| contains_post_cars | NO | 0.0 |  |
| contains_get_cars | NO | 0.0 |  |
| contains_get_cars_plate | YES | 0.8 |  |
| contains_health_endpoint | YES | 1.0 |  |
| contains_node_check | YES | 1.0 |  |
| contains_pydantic_model | YES | 0.7 |  |
| contains_http_exception | YES | 0.6 |  |
| contains_uvicorn_main | YES | 0.6 |  |

#### Model response

```text
This is a Python script that uses FastAPI for creating an API, SQLite for database management and Pydantic for data validation. The requirements are as follows:

1. FastAPI to create the API.
2. SQLite database for storing cars.
3. A 'cars' table in the database with fields like id, plate, owner, and created_at.
4. POST /cars endpoint to add a car.
5. GET /cars endpoint to get all cars.
6. GET /cars/{plate} endpoint to search for a car by its plate number.
7. GET /health endpoint to check the health of the system.
8. The health endpoint should check:
   - If SQLite is accessible.
   - The Python version.
   - If Node.js (via node --version) is installed.
9. If Node.js is not installed, the server should not fail. Return a status of node_installed=false in the health endpoint.
10. Use Pydantic for data validation.
11. Add error handling to FastAPI using HTTPException.
12. The script should include a block at the end to run the server with uvicorn:
    if __name__ == "__main__":
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8010)

Please note that this is a basic script and does not include all the requirements you mentioned in your question. Also, it assumes that FastAPI, SQLite, Pydantic and uvicorn are installed in your Python environment.
```

#### Human/AI notes

```text
Заполни этот блок позже при ручной или AI-оценке. Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.
```

<!-- BENCH_RESULT {"duration_seconds": 38.876, "model_name": "deepseek-coder:1.3b", "prompt_id": "PROMPT-F42A416EEC074CA7", "run_id": "RUN-20260510-204751-M4XQ9GJ9", "score_total": 9.76, "status": "OK", "test_case_id": "fastapi_sqlite_node_health"} -->

### MODEL_RESULT: deepseek-coder:1.3b

| Метрика | Значение |
| --- | --- |
| run_id | RUN-20260510-204751-M4XQ9GJ9 |
| test_case_id | fastapi_sqlite_node_health |
| prompt_id | PROMPT-F42A416EEC074CA7 |
| model_name | deepseek-coder:1.3b |
| status | OK |
| http_status_code | 200 |
| duration_seconds | 38.88 |
| duration_hms | 0:00:39 |
| output_tokens | 700 |
| tokens_per_second | 25.57 |
| response_chars | 2629 |
| total_duration_ns | 36828826500 |
| load_duration_ns | 1209294800 |
| prompt_eval_count | 612 |
| prompt_eval_duration_ns | 6610276100 |
| eval_count | 700 |
| eval_duration_ns | 27372799000 |
| auto_quality_score | 10.0 |
| speed_score | 8.8 |
| stability_score | 10.0 |
| score_total | 9.76 |

#### Auto checks

| Проверка | Результат | Баллы | Комментарий |
| --- | --- | --- | --- |
| contains_fastapi_import | YES | 1.3 |  |
| contains_sqlite | YES | 1.2 |  |
| contains_cars_table | YES | 1.0 |  |
| contains_post_cars | YES | 1.0 |  |
| contains_get_cars | NO | 0.0 |  |
| contains_get_cars_plate | NO | 0.0 |  |
| contains_health_endpoint | NO | 0.0 |  |
| contains_node_check | NO | 0.0 |  |
| contains_pydantic_model | YES | 0.7 |  |
| contains_http_exception | YES | 0.6 |  |
| contains_uvicorn_main | NO | 0.0 |  |

#### Model response

````text
```python
from fastapi import FastAPI, HTTPException
import sqlite3
from datetime import datetime
from pydantic import BaseModel

app = FastAPI()

# Connect to SQLite database and create table if not exists
conn = sqlite3.connect('cars.db')  # Create a connection object using the 'sqlite' module, which returns an instance of Cursor class that provides methods for executing statements in DBMS (Database Management System) like CREATE TABLE etc., to execute SQL commands on database server and fetch results
cur = conn.cursor()  
# Execute command: create table if not exists cars(id INTEGER PRIMARY KEY AUTOINCREMENT, plate TEXT UNIQUE NOT NULL, owner TEXT NOT NULL, created_at TEXT NOT NULL) in the SQLite database server (cars.db file).  This will be executed only once when you run your script for first time
cur.execute('''CREATE TABLE IF NOT EXISTS cars(id INTEGER PRIMARY KEY AUTOINCREMENT, plate TEXT UNIQUE NOT NULL, owner TEXT NOT NULL, created_at TEXT NOT NULL)''')   # Commit the changes and close connection to database server (cars.db file).
conn.close() 

class Car(BaseModel):
    id: int | None = None
    plate: str
    owner: str
    created_at: datetime | None = None
    
@app.post("/cars/")   # FastAPI decorator to define a POST endpoint at /cars/. This function will be called when you send HTTP request with method=POST and path is "/cars/" in your application, then it's going to add new car into the database using data from body of http response.
def create_car(newCar: Car):   # FastAPI parameter decorator that takes a Pydantic model (in this case 'Car') as input and validates its structure against defined schema in function parameters, then it's going to add new car into the database using data from body of http response.
    conn = sqlite3.connect('cars.db', detect_types=sqlite3.PARSE_DECLTYPES)  # Connecting SQLite DB with 'detect types'. This will help FastAPI to automatically convert request's JSON content into Python data type (like str, int etc.)
    cur = conn.cursor()  
    
    newCarPlateOwnerCreatedAtFormatStr =  f"{newCar.plate} {newCar.owner} {str(datetime.now().date()) } "  # Formatting the date in format 'YYYY-MM-DD' for SQLite database compatibility (current_timestamp() is not supported by sqlite3)
    newCarCreatedAt = datetime.now()   # Getting current timestamp when car created, it will be used as `created at` field of cars table 
    
    cur.execute(f"INSERT INTO cars VALUES ('{newCarPlateOwnerCreatedAtFormatStr}')")  # Execute SQL command to insert new row into 'cars' database (table) with data from request body, using placeholders for values in the query
````

#### Human/AI notes

```text
Заполни этот блок позже при ручной или AI-оценке. Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.
```

<!-- BENCH_RESULT {"duration_seconds": 50.387, "model_name": "qwen2.5-coder:3b", "prompt_id": "PROMPT-F42A416EEC074CA7", "run_id": "RUN-20260510-204751-M4XQ9GJ9", "score_total": 9.6, "status": "OK", "test_case_id": "fastapi_sqlite_node_health"} -->

### MODEL_RESULT: qwen2.5-coder:3b

| Метрика | Значение |
| --- | --- |
| run_id | RUN-20260510-204751-M4XQ9GJ9 |
| test_case_id | fastapi_sqlite_node_health |
| prompt_id | PROMPT-F42A416EEC074CA7 |
| model_name | qwen2.5-coder:3b |
| status | OK |
| http_status_code | 200 |
| duration_seconds | 50.39 |
| duration_hms | 0:00:50 |
| output_tokens | 491 |
| tokens_per_second | 13.85 |
| response_chars | 1925 |
| total_duration_ns | 48340564600 |
| load_duration_ns | 3020110300 |
| prompt_eval_count | 398 |
| prompt_eval_duration_ns | 8151702800 |
| eval_count | 491 |
| eval_duration_ns | 35451669200 |
| auto_quality_score | 10.0 |
| speed_score | 8.0 |
| stability_score | 10.0 |
| score_total | 9.6 |

#### Auto checks

| Проверка | Результат | Баллы | Комментарий |
| --- | --- | --- | --- |
| contains_fastapi_import | YES | 1.3 |  |
| contains_sqlite | YES | 1.2 |  |
| contains_cars_table | NO | 0.0 |  |
| contains_post_cars | YES | 1.0 |  |
| contains_get_cars | YES | 0.8 |  |
| contains_get_cars_plate | YES | 0.8 |  |
| contains_health_endpoint | YES | 1.0 |  |
| contains_node_check | YES | 1.0 |  |
| contains_pydantic_model | YES | 0.7 |  |
| contains_http_exception | YES | 0.6 |  |
| contains_uvicorn_main | YES | 0.6 |  |

#### Model response

````text
```python
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import sqlite3
from datetime import datetime

app = FastAPI()

# Pydantic model for car data
class Car(BaseModel):
    plate: str
    owner: str

def get_db():
    conn = sqlite3.connect('cars.db')
    try:
        yield conn
    finally:
        conn.close()

@app.post("/cars", response_model=Car)
async def add_car(car: Car, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("INSERT INTO cars (plate, owner, created_at) VALUES (?, ?, ?)",
                  (car.plate, car.owner, datetime.now()))
    db.commit()
    return car

@app.get("/cars")
async def get_cars(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM cars")
    rows = cursor.fetchall()
    return [{"id": row[0], "plate": row[1], "owner": row[2], "created_at": row[3]} for row in rows]

@app.get("/cars/{plate}")
async def get_car_by_plate(plate: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM cars WHERE plate=?", (plate,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Car not found")
    return {"id": row[0], "plate": row[1], "owner": row[2], "created_at": row[3]}

@app.get("/health")
async def health():
    node_installed = False
    try:
        import subprocess
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            node_installed = True
    except FileNotFoundError:
        pass

    return {
        "sqlite": sqlite3.connect('cars.db').closed,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "node_installed": node_installed
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
```
````

#### Human/AI notes

```text
Заполни этот блок позже при ручной или AI-оценке. Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.
```

<!-- BENCH_RESULT {"duration_seconds": 53.353, "model_name": "codegemma:2b", "prompt_id": "PROMPT-F42A416EEC074CA7", "run_id": "RUN-20260510-204751-M4XQ9GJ9", "score_total": 9.6, "status": "OK", "test_case_id": "fastapi_sqlite_node_health"} -->

### MODEL_RESULT: codegemma:2b

| Метрика | Значение |
| --- | --- |
| run_id | RUN-20260510-204751-M4XQ9GJ9 |
| test_case_id | fastapi_sqlite_node_health |
| prompt_id | PROMPT-F42A416EEC074CA7 |
| model_name | codegemma:2b |
| status | OK |
| http_status_code | 200 |
| duration_seconds | 53.35 |
| duration_hms | 0:00:53 |
| output_tokens | 700 |
| tokens_per_second | 16.98 |
| response_chars | 2950 |
| total_duration_ns | 51275431100 |
| load_duration_ns | 2609323000 |
| prompt_eval_count | 362 |
| prompt_eval_duration_ns | 5516512400 |
| eval_count | 700 |
| eval_duration_ns | 41231903500 |
| auto_quality_score | 10.0 |
| speed_score | 8.0 |
| stability_score | 10.0 |
| score_total | 9.6 |

#### Auto checks

| Проверка | Результат | Баллы | Комментарий |
| --- | --- | --- | --- |
| contains_fastapi_import | NO | 0.0 |  |
| contains_sqlite | YES | 1.2 |  |
| contains_cars_table | NO | 0.0 |  |
| contains_post_cars | NO | 0.0 |  |
| contains_get_cars | NO | 0.0 |  |
| contains_get_cars_plate | NO | 0.0 |  |
| contains_health_endpoint | NO | 0.0 |  |
| contains_node_check | YES | 1.0 |  |
| contains_pydantic_model | NO | 0.0 |  |
| contains_http_exception | NO | 0.0 |  |
| contains_uvicorn_main | NO | 0.0 |  |

#### Model response

```text


Подсказка:
- Для проверки SQLite доступности используй sqlite3.connect(database="cars.db").
- Для проверки Python версии используй sys.version.
- Для проверки Node версии используй node --version.
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии используй subprocess.run(["node", "--version"], capture_output=True).
- Для проверки Node версии использу
```

#### Human/AI notes

```text
Заполни этот блок позже при ручной или AI-оценке. Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.
```

<!-- BENCH_RESULT {"duration_seconds": 79.116, "model_name": "granite-code:3b", "prompt_id": "PROMPT-F42A416EEC074CA7", "run_id": "RUN-20260510-204751-M4XQ9GJ9", "score_total": 9.2, "status": "OK", "test_case_id": "fastapi_sqlite_node_health"} -->

### MODEL_RESULT: granite-code:3b

| Метрика | Значение |
| --- | --- |
| run_id | RUN-20260510-204751-M4XQ9GJ9 |
| test_case_id | fastapi_sqlite_node_health |
| prompt_id | PROMPT-F42A416EEC074CA7 |
| model_name | granite-code:3b |
| status | OK |
| http_status_code | 200 |
| duration_seconds | 79.12 |
| duration_hms | 0:01:19 |
| output_tokens | 465 |
| tokens_per_second | 7.92 |
| response_chars | 1614 |
| total_duration_ns | 77092783700 |
| load_duration_ns | 2750376200 |
| prompt_eval_count | 461 |
| prompt_eval_duration_ns | 14306462400 |
| eval_count | 465 |
| eval_duration_ns | 58712594800 |
| auto_quality_score | 10.0 |
| speed_score | 6.0 |
| stability_score | 10.0 |
| score_total | 9.2 |

#### Auto checks

| Проверка | Результат | Баллы | Комментарий |
| --- | --- | --- | --- |
| contains_fastapi_import | YES | 1.3 |  |
| contains_sqlite | YES | 1.2 |  |
| contains_cars_table | NO | 0.0 |  |
| contains_post_cars | YES | 1.0 |  |
| contains_get_cars | YES | 0.8 |  |
| contains_get_cars_plate | YES | 0.8 |  |
| contains_health_endpoint | YES | 1.0 |  |
| contains_node_check | YES | 1.0 |  |
| contains_pydantic_model | YES | 0.7 |  |
| contains_http_exception | YES | 0.6 |  |
| contains_uvicorn_main | YES | 0.6 |  |

#### Model response

````text
```python
import sqlite3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os

app = FastAPI()

class Car(BaseModel):
    plate: str
    owner: str

@app.post("/cars")
def add_car(car: Car):
    conn = sqlite3.connect("cars.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO cars (plate, owner) VALUES (?, ?)", (car.plate, car.owner))
        conn.commit()
        return {"message": "Car added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to add car") from e

@app.get("/cars")
def get_cars():
    conn = sqlite3.connect("cars.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cars")
    cars = cursor.fetchall()
    return {"cars": [dict(car) for car in cars]}

@app.get("/cars/{plate}")
def get_car_by_plate(plate: str):
    conn = sqlite3.connect("cars.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cars WHERE plate=?", (plate,))
    car = cursor.fetchone()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    return {"car": dict(car)}

@app.get("/health")
def check_health():
    health = {
        "sqlite_available": True,
        "python_version": f"{os.name} {os.uname().release}",
        "node_installed": False
    }

    try:
        import subprocess
        output = subprocess.check_output(["node", "--version"])
        health["node_installed"] = True
    except Exception as e:
        pass

    return health

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
```
````

#### Human/AI notes

```text
Заполни этот блок позже при ручной или AI-оценке. Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.
```

<!-- BENCH_RESULT {"duration_seconds": 95.541, "model_name": "stable-code:3b", "prompt_id": "PROMPT-F42A416EEC074CA7", "run_id": "RUN-20260510-204751-M4XQ9GJ9", "score_total": 9.2, "status": "OK", "test_case_id": "fastapi_sqlite_node_health"} -->

### MODEL_RESULT: stable-code:3b

| Метрика | Значение |
| --- | --- |
| run_id | RUN-20260510-204751-M4XQ9GJ9 |
| test_case_id | fastapi_sqlite_node_health |
| prompt_id | PROMPT-F42A416EEC074CA7 |
| model_name | stable-code:3b |
| status | OK |
| http_status_code | 200 |
| duration_seconds | 95.54 |
| duration_hms | 0:01:36 |
| output_tokens | 700 |
| tokens_per_second | 9.13 |
| response_chars | 2367 |
| total_duration_ns | 93474606600 |
| load_duration_ns | 968628800 |
| prompt_eval_count | 545 |
| prompt_eval_duration_ns | 14031548200 |
| eval_count | 700 |
| eval_duration_ns | 76661423900 |
| auto_quality_score | 10.0 |
| speed_score | 6.0 |
| stability_score | 10.0 |
| score_total | 9.2 |

#### Auto checks

| Проверка | Результат | Баллы | Комментарий |
| --- | --- | --- | --- |
| contains_fastapi_import | YES | 1.3 |  |
| contains_sqlite | YES | 1.2 |  |
| contains_cars_table | NO | 0.0 |  |
| contains_post_cars | YES | 1.0 |  |
| contains_get_cars | YES | 0.8 |  |
| contains_get_cars_plate | YES | 0.8 |  |
| contains_health_endpoint | YES | 1.0 |  |
| contains_node_check | NO | 0.0 |  |
| contains_pydantic_model | YES | 0.7 |  |
| contains_http_exception | YES | 0.6 |  |
| contains_uvicorn_main | NO | 0.0 |  |

#### Model response

````text
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3


class Car(BaseModel):
    plate: str
    owner: str
    created_at: str


def get_db_connection():
    conn = sqlite3.connect('cars.db')
    conn.row_factory = sqlite3.Row
    return conn


app = FastAPI()


@app.post('/cars', response_model=Car))
async def add_car(car: Car):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = '''INSERT INTO cars (plate, owner, created_at) VALUES (?, ?, ?);'''
        data = (car.plate, car.owner, car.created_at))
        cursor.execute(query, data)
        conn.commit()
        return {'message': 'Car added successfully'}
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail="An error occurred while adding the car")) from e


@app.get('/cars', response_model=list))
async def get_cars():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = '''SELECT * FROM cars;'''
        cursor.execute(query)
        rows = cursor.fetchall()
        return [{'id': row['id']}, {'plate': row['plate']}, {'owner': row['owner']}, {'created_at': row['created_at']}]
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail="An error occurred while fetching the cars")) from e


@app.get('/cars/{plate}', response_model=Car))
async def get_car_by_plate(plate: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = '''SELECT * FROM cars WHERE plate=?;'''
        data = (plate,))
        cursor.execute(query, data)
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Car not found"))
        return {'id': row['id']}, {'plate': row['plate']}, {'owner': row['owner']}, {'created_at': row['created_at']}]
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail="An error occurred while fetching the car by plate")) from e


@app.get('/health')
async def health():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = '''SELECT 1;'''
        cursor.execute(query)
        row = cursor.fetchone()
        if row[0] != 1:
            return {'status': 'node_installed=false'}
        version = '.'.join(map(str, (conn.get_server().socket.family
````

#### Human/AI notes

```text
Заполни этот блок позже при ручной или AI-оценке. Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.
```

<!-- BENCH_RESULT {"duration_seconds": 15.939, "model_name": "starcoder2:3b", "prompt_id": "PROMPT-F42A416EEC074CA7", "run_id": "RUN-20260510-204751-M4XQ9GJ9", "score_total": 2.75, "status": "OK", "test_case_id": "fastapi_sqlite_node_health"} -->

### MODEL_RESULT: starcoder2:3b

| Метрика | Значение |
| --- | --- |
| run_id | RUN-20260510-204751-M4XQ9GJ9 |
| test_case_id | fastapi_sqlite_node_health |
| prompt_id | PROMPT-F42A416EEC074CA7 |
| model_name | starcoder2:3b |
| status | OK |
| http_status_code | 200 |
| duration_seconds | 15.94 |
| duration_hms | 0:00:16 |
| output_tokens | 2 |
| tokens_per_second | 22.81 |
| response_chars | 1 |
| total_duration_ns | 13891349200 |
| load_duration_ns | 2241452600 |
| prompt_eval_count | 471 |
| prompt_eval_duration_ns | 11555771300 |
| eval_count | 2 |
| eval_duration_ns | 87692300 |
| auto_quality_score | 0.0 |
| speed_score | 10.0 |
| stability_score | 5.0 |
| score_total | 2.75 |

#### Auto checks

| Проверка | Результат | Баллы | Комментарий |
| --- | --- | --- | --- |
| contains_fastapi_import | NO | 0.0 |  |
| contains_sqlite | NO | 0.0 |  |
| contains_cars_table | NO | 0.0 |  |
| contains_post_cars | NO | 0.0 |  |
| contains_get_cars | NO | 0.0 |  |
| contains_get_cars_plate | NO | 0.0 |  |
| contains_health_endpoint | NO | 0.0 |  |
| contains_node_check | NO | 0.0 |  |
| contains_pydantic_model | NO | 0.0 |  |
| contains_http_exception | NO | 0.0 |  |
| contains_uvicorn_main | NO | 0.0 |  |

#### Error

```text
Empty response text.
```

#### Model response

```text

```

#### Human/AI notes

```text
Заполни этот блок позже при ручной или AI-оценке. Например: рабочий код, неполный код, нарушил инструкцию, зависал, хороший кандидат.
```

## RUN SUMMARY RANKING

| rank | model | tests | ok | errors | avg_score | avg_quality | avg_speed | avg_duration_sec | avg_tokens_sec |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | yi-coder:1.5b | 1 | 1 | 0 | 10.0 | 10.0 | 10.0 | 25.66 | 22.68 |
| 2 | qwen2.5-coder:1.5b | 1 | 1 | 0 | 10.0 | 10.0 | 10.0 | 28.36 | 27.24 |
| 3 | deepseek-coder:1.3b | 1 | 1 | 0 | 9.76 | 10.0 | 8.8 | 38.88 | 25.57 |
| 4 | qwen2.5-coder:3b | 1 | 1 | 0 | 9.6 | 10.0 | 8.0 | 50.39 | 13.85 |
| 5 | codegemma:2b | 1 | 1 | 0 | 9.6 | 10.0 | 8.0 | 53.35 | 16.98 |
| 6 | granite-code:3b | 1 | 1 | 0 | 9.2 | 10.0 | 6.0 | 79.12 | 7.92 |
| 7 | stable-code:3b | 1 | 1 | 0 | 9.2 | 10.0 | 6.0 | 95.54 | 9.13 |
| 8 | starcoder2:3b | 1 | 1 | 0 | 2.75 | 0.0 | 10.0 | 15.94 | 22.81 |

## RUN ANALYSIS PROMPT

```text
Проанализируй этот RUN_ID: RUN-20260510-204751-M4XQ9GJ9.

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
```
