<#
run_benchmark_with_download.ps1

Назначение:
  1. Сначала скачивает/проверяет Ollama-модели обычным интерактивным прогрессом `ollama pull`.
  2. При ошибке скачивания повторяет попытку до 3 раз.
  3. После скачивания запускает Python benchmark-скрипт с флагом --no-pull.
  4. В benchmark передаются только успешно скачанные/проверенные модели.

Примеры:
  .\run_benchmark_with_download.ps1
  .\run_benchmark_with_download.ps1 -PullSet quick
  .\run_benchmark_with_download.ps1 -PullSet uploaded -Full
  .\run_benchmark_with_download.ps1 -Model qwen2.5-coder:3b -Model codegemma:2b
  .\run_benchmark_with_download.ps1 -Model qwen2.5-coder:3b -- --rerun-existing
#>

[CmdletBinding()]
param(
    [ValidateSet("uploaded", "quick", "cpu", "heavy", "all")]
    [string]$PullSet = "uploaded",

    [string[]]$Model = @(),

    [int]$Retries = 3,

    [switch]$Full,

    [switch]$NoPause,

    [string]$BenchmarkScript = "",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs = @()
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $ScriptDir "benchmark_download_and_run.log"

# Модели из твоего рабочего download_models.ps1
$UploadedModels = @(
    "stable-code:3b",
    "deepseek-coder:6.7b",
    "yi-coder:1.5b",
    "phi3:mini",
    "llama3.2:3b",
    "mistral:7b-instruct-v0.3",
    "codellama:7b-instruct"
)

# Быстрый набор, который раньше показал смысл для CPU-кодинга
$QuickModels = @(
    "qwen2.5-coder:3b",
    "codegemma:2b",
    "qwen2.5-coder:1.5b"
)

# Основной CPU-набор
$CpuModels = @(
    "qwen2.5-coder:1.5b",
    "qwen2.5-coder:3b",
    "codegemma:2b",
    "deepseek-coder:1.3b",
    "starcoder2:3b",
    "granite-code:3b",
    "stable-code:3b",
    "yi-coder:1.5b",
    "llama3.2:3b",
    "phi3:mini"
)

# Тяжёлые модели. На CPU могут быть медленными.
$HeavyModels = @(
    "qwen2.5-coder:7b",
    "deepseek-coder:6.7b",
    "codellama:7b-instruct",
    "mistral:7b-instruct-v0.3"
)

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO",
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )

    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$time] [$Level] $Message"
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Get-UniqueList {
    param([string[]]$Items)

    $seen = @{}
    $result = New-Object System.Collections.Generic.List[string]

    foreach ($item in $Items) {
        $value = [string]$item
        $value = $value.Trim()
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }
        if (-not $seen.ContainsKey($value)) {
            $seen[$value] = $true
            [void]$result.Add($value)
        }
    }

    return $result.ToArray()
}

function Resolve-Models {
    if ($Model -and $Model.Count -gt 0) {
        return Get-UniqueList -Items $Model
    }

    switch ($PullSet) {
        "uploaded" { return Get-UniqueList -Items $UploadedModels }
        "quick"    { return Get-UniqueList -Items $QuickModels }
        "cpu"      { return Get-UniqueList -Items $CpuModels }
        "heavy"    { return Get-UniqueList -Items $HeavyModels }
        "all"      { return Get-UniqueList -Items ($CpuModels + $HeavyModels + $UploadedModels) }
        default     { return Get-UniqueList -Items $UploadedModels }
    }
}

function Resolve-BenchmarkScript {
    param([string]$Requested)

    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        $candidate = $Requested
        if (-not [System.IO.Path]::IsPathRooted($candidate)) {
            $candidate = Join-Path $ScriptDir $candidate
        }
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
        throw "Benchmark script не найден: $Requested"
    }

    $candidates = @(
        "model_performance_test_v7.py",
        "model_performance_test_v6.py",
        "model_performance_test_v5.py",
        "model_performance_test.py"
    )

    foreach ($name in $candidates) {
        $path = Join-Path $ScriptDir $name
        if (Test-Path $path) {
            return (Resolve-Path $path).Path
        }
    }

    throw "Не найден benchmark script. Положи рядом model_performance_test_v7.py или укажи -BenchmarkScript."
}

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Pull-OneModel {
    param(
        [string]$ModelName,
        [int]$MaxRetries
    )

    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        Write-Host ""
        Write-Host "--------------------------------------------------" -ForegroundColor DarkGray
        Write-Log "PULL START | model=$ModelName | attempt=$attempt/$MaxRetries" "INFO" ([ConsoleColor]::Cyan)
        Write-Host "Сейчас будет обычный интерактивный прогресс Ollama..." -ForegroundColor DarkGray

        $start = Get-Date

        # Важно: вывод НЕ перехватываем. Так Ollama сам рисует прогресс как умеет.
        & ollama pull $ModelName
        $exitCode = $LASTEXITCODE

        $seconds = [Math]::Round(((Get-Date) - $start).TotalSeconds, 2)

        if ($exitCode -eq 0) {
            Write-Log "PULL OK | model=$ModelName | attempt=$attempt/$MaxRetries | seconds=$seconds" "OK" ([ConsoleColor]::Green)
            return $true
        }

        Write-Log "PULL ERROR | model=$ModelName | attempt=$attempt/$MaxRetries | exit_code=$exitCode | seconds=$seconds" "ERROR" ([ConsoleColor]::Red)

        if ($attempt -lt $MaxRetries) {
            Write-Host "Пробую убрать возможную битую загрузку и скачать заново..." -ForegroundColor Yellow
            & ollama rm $ModelName 2>$null | Out-Null
            Start-Sleep -Seconds 5
        }
    }

    Write-Log "PULL FAILED | model=$ModelName | attempts=$MaxRetries" "ERROR" ([ConsoleColor]::Red)
    return $false
}

Clear-Host
Write-Log "============================================================" "INFO" ([ConsoleColor]::Gray)
Write-Log "Запуск: скачать модели, потом запустить benchmark" "INFO" ([ConsoleColor]::Cyan)
Write-Log "Лог: $LogFile" "INFO" ([ConsoleColor]::Gray)
Write-Log "PullSet: $PullSet | Retries: $Retries" "INFO" ([ConsoleColor]::Gray)
Write-Log "============================================================" "INFO" ([ConsoleColor]::Gray)

if (-not (Test-CommandExists "ollama")) {
    Write-Log "Команда ollama не найдена в PATH." "ERROR" ([ConsoleColor]::Red)
    exit 1
}

if (-not (Test-CommandExists "py")) {
    Write-Log "Команда py не найдена. Python Launcher не установлен или не в PATH." "ERROR" ([ConsoleColor]::Red)
    exit 1
}

try {
    $ResolvedBenchmarkScript = Resolve-BenchmarkScript -Requested $BenchmarkScript
    Write-Log "Benchmark script: $ResolvedBenchmarkScript" "INFO" ([ConsoleColor]::Gray)
}
catch {
    Write-Log $_.Exception.Message "ERROR" ([ConsoleColor]::Red)
    exit 1
}

$ModelsToPull = Resolve-Models

Write-Host ""
Write-Host "Модели для скачивания и тестирования:" -ForegroundColor Cyan
for ($i = 0; $i -lt $ModelsToPull.Count; $i++) {
    Write-Host ("{0}. {1}" -f ($i + 1), $ModelsToPull[$i])
}

$OkModels = New-Object System.Collections.Generic.List[string]
$FailedModels = New-Object System.Collections.Generic.List[string]

foreach ($m in $ModelsToPull) {
    $ok = Pull-OneModel -ModelName $m -MaxRetries $Retries
    if ($ok) {
        [void]$OkModels.Add($m)
    }
    else {
        [void]$FailedModels.Add($m)
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkGray
Write-Host "ИТОГ СКАЧИВАНИЯ" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkGray
Write-Host "OK:" -ForegroundColor Green
foreach ($m in $OkModels) {
    Write-Host "  - $m" -ForegroundColor Green
}

if ($FailedModels.Count -gt 0) {
    Write-Host "FAILED:" -ForegroundColor Red
    foreach ($m in $FailedModels) {
        Write-Host "  - $m" -ForegroundColor Red
    }
}

if ($OkModels.Count -eq 0) {
    Write-Log "Нет успешно скачанных моделей. Benchmark не запускаю." "ERROR" ([ConsoleColor]::Red)
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkGray
Write-Host "ЗАПУСК BENCHMARK" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkGray

$PythonArgs = New-Object System.Collections.Generic.List[string]
[void]$PythonArgs.Add($ResolvedBenchmarkScript)
[void]$PythonArgs.Add("--no-pull")

foreach ($m in $OkModels) {
    [void]$PythonArgs.Add("--model")
    [void]$PythonArgs.Add($m)
}

if ($Full) {
    [void]$PythonArgs.Add("--full")
}

if ($NoPause) {
    [void]$PythonArgs.Add("--no-pause")
}

foreach ($arg in $ExtraArgs) {
    if ($arg -eq "--") {
        continue
    }
    [void]$PythonArgs.Add($arg)
}

Write-Log "PYTHON START | py $($PythonArgs -join ' ')" "INFO" ([ConsoleColor]::Cyan)
& py @PythonArgs
$benchmarkExit = $LASTEXITCODE
Write-Log "PYTHON END | exit_code=$benchmarkExit" "INFO" ([ConsoleColor]::Cyan)

if (-not $NoPause) {
    Write-Host ""
    Read-Host "Нажми Enter для выхода"
}

exit $benchmarkExit
