# download_models_retry.ps1
# Массовая загрузка моделей Ollama с повторной перезакачкой при digest mismatch / сбое скачивания.
# Если Ollama пишет "digest mismatch" или "file must be downloaded again",
# скрипт повторит скачивание модели до 3 раз.

$ErrorActionPreference = "Continue"

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

$MaxAttempts = 3
$RetryDelaySeconds = 5
$LogFile = Join-Path $PSScriptRoot "download_models.log"

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$time] [$Level] $Message"

    switch ($Level) {
        "OK"    { Write-Host $line -ForegroundColor Green }
        "WARN"  { Write-Host $line -ForegroundColor Yellow }
        "ERROR" { Write-Host $line -ForegroundColor Red }
        default { Write-Host $line }
    }

    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Test-OllamaCommand {
    $cmd = Get-Command "ollama" -ErrorAction SilentlyContinue

    if (-not $cmd) {
        Write-Log "Ollama не найден в PATH. Установи Ollama или перезапусти PowerShell после установки." "ERROR"
        return $false
    }

    Write-Log "Ollama найден: $($cmd.Source)" "OK"
    return $true
}

function Test-ShouldRetryPull {
    param(
        [string]$OutputText
    )

    # Ошибки, при которых есть смысл повторить скачивание.
    # В твоём случае была ошибка:
    # digest mismatch, file must be downloaded again
    $retryPatterns = @(
        "digest mismatch",
        "file must be downloaded again",
        "sha256",
        "connection reset",
        "connection aborted",
        "timeout",
        "timed out",
        "TLS",
        "unexpected EOF",
        "server misbehaving",
        "i/o timeout"
    )

    foreach ($pattern in $retryPatterns) {
        if ($OutputText -match [regex]::Escape($pattern)) {
            return $true
        }
    }

    return $false
}

function Invoke-OllamaRemoveIfBroken {
    param(
        [string]$ModelName
    )

    Write-Log "Пробую очистить возможную битую/частичную модель перед повторной загрузкой: $ModelName" "WARN"

    try {
        $removeOutput = & ollama rm $ModelName 2>&1

        foreach ($line in $removeOutput) {
            if ($null -ne $line -and $line.ToString().Trim().Length -gt 0) {
                Write-Log "ollama rm: $($line.ToString())" "INFO"
            }
        }
    }
    catch {
        Write-Log "Очистка через ollama rm не выполнена: $($_.Exception.Message). Это не критично, продолжаю." "WARN"
    }
}

function Invoke-OllamaPullWithRetry {
    param(
        [string]$ModelName,
        [int]$MaxAttempts
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Write-Log "Начинаю загрузку: $ModelName | попытка $attempt из $MaxAttempts" "INFO"

        $outputLines = New-Object System.Collections.Generic.List[string]
        $startTime = Get-Date

        try {
            & ollama pull $ModelName 2>&1 | ForEach-Object {
                $line = $_.ToString()
                $outputLines.Add($line) | Out-Null
                Write-Host $line
                Add-Content -Path $LogFile -Value $line -Encoding UTF8
            }

            $exitCode = $LASTEXITCODE
        }
        catch {
            $exitCode = 1
            $line = "PowerShell exception: $($_.Exception.Message)"
            $outputLines.Add($line) | Out-Null
            Write-Log $line "ERROR"
        }

        $endTime = Get-Date
        $duration = [math]::Round(($endTime - $startTime).TotalSeconds, 1)
        $outputText = ($outputLines -join "`n")

        if ($exitCode -eq 0) {
            Write-Log "Успешно скачано: $ModelName | попытка $attempt | время: $duration сек" "OK"
            return @{
                Model = $ModelName
                Status = "OK"
                Attempts = $attempt
                DurationSeconds = $duration
                Error = ""
            }
        }

        $shouldRetry = Test-ShouldRetryPull -OutputText $outputText

        Write-Log "Ошибка при скачивании: $ModelName | попытка $attempt | exitCode=$exitCode | время: $duration сек" "ERROR"

        if ($shouldRetry -and $attempt -lt $MaxAttempts) {
            Write-Log "Ошибка похожа на сбой скачивания/контрольной суммы. Будет повторная перезакачка." "WARN"
            Invoke-OllamaRemoveIfBroken -ModelName $ModelName
            Write-Log "Жду $RetryDelaySeconds сек перед повтором..." "WARN"
            Start-Sleep -Seconds $RetryDelaySeconds
            continue
        }

        if (-not $shouldRetry) {
            Write-Log "Ошибка не похожа на digest mismatch/сбой сети. Повторять бессмысленно, перехожу к следующей модели." "ERROR"
            break
        }

        if ($attempt -ge $MaxAttempts) {
            Write-Log "Модель не скачалась после $MaxAttempts попыток: $ModelName" "ERROR"
            break
        }
    }

    return @{
        Model = $ModelName
        Status = "FAIL"
        Attempts = $MaxAttempts
        DurationSeconds = 0
        Error = "Не удалось скачать модель после $MaxAttempts попыток"
    }
}

Clear-Host

Write-Log "============================================================"
Write-Log "Запуск массовой загрузки моделей для скоринга"
Write-Log "Лог: $LogFile"
Write-Log "Максимум попыток на модель: $MaxAttempts"
Write-Log "============================================================"

if (-not (Test-OllamaCommand)) {
    Read-Host "Нажми Enter для выхода"
    exit 1
}

$results = New-Object System.Collections.Generic.List[object]

foreach ($model in $models) {
    Write-Host "--------------------------------------------------"
    $result = Invoke-OllamaPullWithRetry -ModelName $model -MaxAttempts $MaxAttempts
    $results.Add([PSCustomObject]$result) | Out-Null
}

Write-Log "============================================================"
Write-Log "ИТОГ ЗАГРУЗКИ МОДЕЛЕЙ"
Write-Log "============================================================"

$results | Format-Table Model, Status, Attempts, DurationSeconds, Error -AutoSize

Add-Content -Path $LogFile -Value ""
Add-Content -Path $LogFile -Value "ИТОГ ЗАГРУЗКИ МОДЕЛЕЙ:" -Encoding UTF8
$results | Out-String | Add-Content -Path $LogFile -Encoding UTF8

Write-Log "Все операции завершены. Лог сохранён: $LogFile" "OK"
Read-Host "Нажми Enter для выхода"
