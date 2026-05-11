# Список отобранных моделей для теста на CPU
$models = @(
    "stable-code:3b",
    "deepseek-coder:6.7b",
    "yi-coder:1.5b",
    "phi3:mini",
    "llama3.2:3b",
    "mistral:7b-instruct-v0.3",
    "codellama:7b-instruct"
)

Write-Host "--- Запуск массовой загрузки моделей для скоринга ---" -ForegroundColor Cyan

foreach ($model in $models) {
    Write-Host "--------------------------------------------------"
    Write-Host "Начинаю загрузку: $model" -ForegroundColor Yellow
    
    # Запуск команды ollama pull
    ollama pull $model
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Успешно скачано: $model" -ForegroundColor Green
    } else {
        Write-Host "Ошибка при скачивании: $model" -ForegroundColor Red
    }
}

Write-Host "`nВсе операции завершены!" -ForegroundColor Cyan
pause