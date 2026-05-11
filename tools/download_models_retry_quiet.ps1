# download_models_retry_quiet.ps1
# Тихая массовая загрузка моделей Ollama с 3 попытками.
# Не печатает сырой прогресс ollama pull в консоль, чтобы не было длинного мусорного вывода.
# Все события пишет в один общий лог: download_models.log

$ErrorActionPreference = "Continue"

# -----------------------------
# Настройки
# -----------------------------
$Models = @(
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
$StatusEverySeconds = 10
$LogFile = Join-Path $PSScriptRoot "download_models.log"

# Уменьшаем шанс цветного/ANSI-вывода от CLI.
$env:NO_COLOR = "1"
$env:TERM = "dumb"

# -----------------------------
# Логирование
# -----------------------------
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

function Remove-AnsiAndControlChars {
    param(
        [string]$Text
    )

    if ([string]::IsNullOrEmpty($Text)) {
        return ""
    }

    # Убираем ANSI escape sequences и управляющие символы прогресса.
    $clean = $Text
    $clean = $clean -replace "\x1B\[[0-9;?]*[ -/]*[@-~]", ""
    $clean = $clean -replace "\x1B\][^\x07]*(\x07|\x1B\\)", ""
    $clean = $clean -replace "[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", ""
    $clean = $clean -replace "`r", "`n"
    return $clean
}

function Get-LastUsefulLines {
    param(
        [string]$Text,
        [int]$MaxLines = 40
    )

    $clean = Remove-AnsiAndControlChars -Text $Text
    $lines = $clean -split "`n" |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_.Length -gt 0 }

    if ($lines.Count -le $MaxLines) {
        return ($lines -join "`n")
    }

    return (($lines | Select-Object -Last $MaxLines) -join "`n")
}

# -----------------------------
# Проверки и служебные функции
# -----------------------------
function Get-OllamaCommandPath {
    $cmd = Get-Command "ollama" -ErrorAction SilentlyContinue

    if (-not $cmd) {
        Write-Log "Ollama не найден в PATH. Установи Ollama или перезапусти PowerShell после установки." "ERROR"
        return $null
    }

    Write-Log "Ollama найден: $($cmd.Source)" "OK"
    return $cmd.Source
}

function Test-ModelAlreadyInstalled {
    param(
        [string]$ModelName
    )

    try {
        $listOutput = & ollama list 2>$null
        foreach ($line in $listOutput) {
            if ($line -match "^\s*$([regex]::Escape($ModelName))\s+") {
                return $true
            }
        }
    }
    catch {
        return $false
    }

    return $false
}

function Test-ShouldRetryPull {
    param(
        [string]$OutputText
    )

    $clean = Remove-AnsiAndControlChars -Text $OutputText

    $retryPatterns = @(
        "digest mismatch",
        "file must be downloaded again",
        "connection reset",
        "connection aborted",
        "timeout",
        "timed out",
        "TLS",
        "unexpected EOF",
        "server misbehaving",
        "i/o timeout",
        "EOF",
        "temporary",
        "try again"
    )

    foreach ($pattern in $retryPatterns) {
        if ($clean -match [regex]::Escape($pattern)) {
            return $true
        }
    }

    return $false
}

function Get-DigestMismatchExpectedSha {
    param(
        [string]$OutputText
    )

    $clean = Remove-AnsiAndControlChars -Text $OutputText

    # Пример:
    # want sha256:2c0d857..., got sha256:d73133...
    $match = [regex]::Match($clean, "want\s+sha256:([a-fA-F0-9]{32,128})")
    if ($match.Success) {
        return $match.Groups[1].Value.ToLowerInvariant()
    }

    return $null
}

function Remove-BrokenOllamaBlobIfFound {
    param(
        [string]$OutputText
    )

    $expectedSha = Get-DigestMismatchExpectedSha -OutputText $OutputText

    if ([string]::IsNullOrWhiteSpace($expectedSha)) {
        return
    }

    $blobPath = Join-Path $env:USERPROFILE ".ollama\models\blobs\sha256-$expectedSha"

    if (Test-Path $blobPath) {
        try {
            Remove-Item -Path $blobPath -Force
            Write-Log "Удалён повреждённый blob Ollama: $blobPath" "WARN"
        }
        catch {
            Write-Log "Не смог удалить повреждённый blob: $blobPath | $($_.Exception.Message)" "WARN"
        }
    }
    else {
        Write-Log "Digest mismatch найден, но blob-файл не найден по пути: $blobPath" "WARN"
    }
}

function Invoke-OllamaRemoveIfNeeded {
    param(
        [string]$ModelName
    )

    try {
        $removeOutput = & ollama rm $ModelName 2>&1
        $removeText = ($removeOutput -join "`n")
        $shortRemoveText = Get-LastUsefulLines -Text $removeText -MaxLines 10

        if (-not [string]::IsNullOrWhiteSpace($shortRemoveText)) {
            Add-Content -Path $LogFile -Value "ollama rm $ModelName output:" -Encoding UTF8
            Add-Content -Path $LogFile -Value $shortRemoveText -Encoding UTF8
        }
    }
    catch {
        Write-Log "ollama rm $ModelName не выполнен: $($_.Exception.Message). Это не критично." "WARN"
    }
}

# -----------------------------
# Тихий запуск ollama pull
# -----------------------------
function Invoke-OllamaPullQuiet {
    param(
        [string]$OllamaPath,
        [string]$ModelName,
        [int]$Attempt
    )

    $safeModelFileName = $ModelName -replace "[^a-zA-Z0-9_.-]", "_"
    $stdoutFile = Join-Path $env:TEMP "ollama_pull_${safeModelFileName}_attempt_${Attempt}_stdout.txt"
    $stderrFile = Join-Path $env:TEMP "ollama_pull_${safeModelFileName}_attempt_${Attempt}_stderr.txt"

    Remove-Item -Path $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue

    $startTime = Get-Date
    $lastStatusTime = Get-Date

    Write-Log "Начинаю загрузку: $ModelName | попытка $Attempt из $MaxAttempts" "INFO"
    Write-Host "    Идёт скачивание. Сырой прогресс скрыт, чтобы не засорять окно..." -ForegroundColor DarkGray

    try {
        $process = Start-Process `
            -FilePath $OllamaPath `
            -ArgumentList @("pull", $ModelName) `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError $stderrFile `
            -NoNewWindow `
            -PassThru

        while (-not $process.HasExited) {
            Start-Sleep -Seconds 1

            $now = Get-Date
            if (($now - $lastStatusTime).TotalSeconds -ge $StatusEverySeconds) {
                $elapsed = [math]::Round(($now - $startTime).TotalSeconds, 0)
                Write-Host "    $ModelName ещё скачивается... прошло $elapsed сек" -ForegroundColor DarkGray
                $lastStatusTime = $now
            }
        }

        $process.WaitForExit()
        $exitCode = $process.ExitCode
    }
    catch {
        $exitCode = 1
        $exceptionText = "PowerShell exception: $($_.Exception.Message)"
        Set-Content -Path $stderrFile -Value $exceptionText -Encoding UTF8
    }

    $endTime = Get-Date
    $duration = [math]::Round(($endTime - $startTime).TotalSeconds, 1)

    $stdoutText = ""
    $stderrText = ""

    if (Test-Path $stdoutFile) {
        $stdoutText = Get-Content -Path $stdoutFile -Raw -ErrorAction SilentlyContinue
    }

    if (Test-Path $stderrFile) {
        $stderrText = Get-Content -Path $stderrFile -Raw -ErrorAction SilentlyContinue
    }

    $combinedText = "$stdoutText`n$stderrText"
    $shortText = Get-LastUsefulLines -Text $combinedText -MaxLines 60

    Remove-Item -Path $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue

    return [PSCustomObject]@{
        ExitCode = $exitCode
        DurationSeconds = $duration
        OutputText = $combinedText
        ShortOutputText = $shortText
    }
}

function Invoke-OllamaPullWithRetry {
    param(
        [string]$OllamaPath,
        [string]$ModelName,
        [int]$MaxAttempts
    )

    if (Test-ModelAlreadyInstalled -ModelName $ModelName) {
        Write-Log "Модель уже установлена, пропускаю скачивание: $ModelName" "OK"
        return [PSCustomObject]@{
            Model = $ModelName
            Status = "ALREADY_INSTALLED"
            Attempts = 0
            DurationSeconds = 0
            Error = ""
        }
    }

    $lastError = ""
    $totalDuration = 0

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $result = Invoke-OllamaPullQuiet -OllamaPath $OllamaPath -ModelName $ModelName -Attempt $attempt
        $totalDuration += $result.DurationSeconds

        if ($result.ExitCode -eq 0) {
            Write-Log "Успешно скачано: $ModelName | попытка $attempt | время: $($result.DurationSeconds) сек" "OK"
            return [PSCustomObject]@{
                Model = $ModelName
                Status = "OK"
                Attempts = $attempt
                DurationSeconds = [math]::Round($totalDuration, 1)
                Error = ""
            }
        }

        $lastError = $result.ShortOutputText
        Write-Log "Ошибка при скачивании: $ModelName | попытка $attempt | exitCode=$($result.ExitCode) | время: $($result.DurationSeconds) сек" "ERROR"

        Add-Content -Path $LogFile -Value "" -Encoding UTF8
        Add-Content -Path $LogFile -Value "--- Краткий вывод ошибки для $ModelName, попытка $attempt ---" -Encoding UTF8
        Add-Content -Path $LogFile -Value $result.ShortOutputText -Encoding UTF8
        Add-Content -Path $LogFile -Value "--- Конец вывода ошибки ---" -Encoding UTF8
        Add-Content -Path $LogFile -Value "" -Encoding UTF8

        $shouldRetry = Test-ShouldRetryPull -OutputText $result.OutputText

        if ($shouldRetry -and $attempt -lt $MaxAttempts) {
            Write-Log "Ошибка похожа на сбой скачивания/контрольной суммы. Пробую подготовить повторную перезакачку." "WARN"
            Remove-BrokenOllamaBlobIfFound -OutputText $result.OutputText
            Invoke-OllamaRemoveIfNeeded -ModelName $ModelName
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

    return [PSCustomObject]@{
        Model = $ModelName
        Status = "FAIL"
        Attempts = $MaxAttempts
        DurationSeconds = [math]::Round($totalDuration, 1)
        Error = ($lastError -replace "`r", " " -replace "`n", " | ")
    }
}

# -----------------------------
# Основной запуск
# -----------------------------
Clear-Host

Write-Log "============================================================"
Write-Log "Запуск тихой массовой загрузки моделей Ollama"
Write-Log "Лог: $LogFile"
Write-Log "Максимум попыток на модель: $MaxAttempts"
Write-Log "Сырой прогресс ollama pull не выводится в консоль"
Write-Log "============================================================"

$OllamaPath = Get-OllamaCommandPath
if ([string]::IsNullOrWhiteSpace($OllamaPath)) {
    Read-Host "Нажми Enter для выхода"
    exit 1
}

$results = New-Object System.Collections.Generic.List[object]

foreach ($model in $Models) {
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    $result = Invoke-OllamaPullWithRetry -OllamaPath $OllamaPath -ModelName $model -MaxAttempts $MaxAttempts
    $results.Add($result) | Out-Null
}

Write-Log "============================================================"
Write-Log "ИТОГ ЗАГРУЗКИ МОДЕЛЕЙ"
Write-Log "============================================================"

$results | Format-Table Model, Status, Attempts, DurationSeconds, Error -AutoSize

Add-Content -Path $LogFile -Value "" -Encoding UTF8
Add-Content -Path $LogFile -Value "ИТОГ ЗАГРУЗКИ МОДЕЛЕЙ:" -Encoding UTF8
$results | Out-String | Add-Content -Path $LogFile -Encoding UTF8

Write-Log "Все операции завершены. Лог сохранён: $LogFile" "OK"
Read-Host "Нажми Enter для выхода"
