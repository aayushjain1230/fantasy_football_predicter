[CmdletBinding()]
param(
    [switch]$SkipBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$envFile = Join-Path $projectRoot ".env"
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvUvicorn = Join-Path $venvDir "Scripts\uvicorn.exe"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        $examplePath = Join-Path $projectRoot ".env.example"
        if (Test-Path -LiteralPath $examplePath) {
            Write-Warning "No .env file found. Loading .env.example for this run. Rename it to .env to keep real credentials out of the public template."
            $Path = $examplePath
        }
        else {
            Write-Warning "No .env file found. The app will start in labeled demo mode."
            return
        }
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) { continue }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return [PSCustomObject]@{ Executable = $py.Path; PrefixArguments = @("-3") }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return [PSCustomObject]@{ Executable = $python.Path; PrefixArguments = @() }
    }

    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundledPython) {
        return [PSCustomObject]@{ Executable = $bundledPython; PrefixArguments = @() }
    }

    throw "Python 3 was not found. Install it from python.org and enable 'Add Python to PATH'."
}

function Find-NodeRunner {
    $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
    if ($pnpm) {
        return [PSCustomObject]@{ Executable = $pnpm.Path; Name = "pnpm" }
    }

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) {
        return [PSCustomObject]@{ Executable = $npm.Path; Name = "npm" }
    }

    $bundledPnpm = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
    if (Test-Path -LiteralPath $bundledPnpm) {
        return [PSCustomObject]@{ Executable = $bundledPnpm; Name = "pnpm" }
    }

    throw "Node.js was not found. Install the free LTS version from nodejs.org."
}

function Find-NodeExecutable {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) { return $node.Path }

    $bundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
    if (Test-Path -LiteralPath $bundledNode) { return $bundledNode }

    throw "Node.js was not found. Install the free LTS version from nodejs.org."
}

Write-Host ""
Write-Host "  FOURTH DOWN" -ForegroundColor DarkYellow
Write-Host "  Starting your fantasy decision engine..." -ForegroundColor Gray
Write-Host ""

Import-DotEnv -Path $envFile

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "First run: creating the Python environment..." -ForegroundColor Cyan
    $pythonCommand = Find-Python
    $pythonExecutable = $pythonCommand.Executable
    $pythonArguments = @($pythonCommand.PrefixArguments)
    $pythonArguments += @("-m", "venv", $venvDir)
    & $pythonExecutable @pythonArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python environment creation failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $venvUvicorn)) {
    Write-Host "First run: installing the backend..." -ForegroundColor Cyan
    & $venvPython -m pip install -e $backendDir
    if ($LASTEXITCODE -ne 0) {
        throw "Backend installation failed. Check the message above, then run the launcher again."
    }
}

$nodeRunner = Find-NodeRunner
$nodeExecutable = $nodeRunner.Executable
$nodeTool = $nodeRunner.Name
$nodeRuntime = Find-NodeExecutable

if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
    Write-Host "First run: installing the website..." -ForegroundColor Cyan
    Push-Location $frontendDir
    try {
        & $nodeExecutable install
        if ($LASTEXITCODE -ne 0) {
            throw "Website installation failed. Check the message above, then run the launcher again."
        }
    }
    finally {
        Pop-Location
    }
}

$backendCommand = "Set-Location -LiteralPath '$($projectRoot.Replace("'", "''"))'; & '$($venvUvicorn.Replace("'", "''"))' app.main:app --app-dir backend --reload"
$nextEntry = Join-Path $frontendDir "node_modules\next\dist\bin\next"
$buildMarker = Join-Path $frontendDir ".next\BUILD_ID"
if (-not (Test-Path -LiteralPath $buildMarker)) {
    Write-Host "First run: building the website..." -ForegroundColor Cyan
    Push-Location $frontendDir
    try {
        & $nodeRuntime $nextEntry build
        if ($LASTEXITCODE -ne 0) {
            throw "Website build failed. Check the message above, then run the launcher again."
        }
    }
    finally {
        Pop-Location
    }
}
$frontendCommand = "Set-Location -LiteralPath '$($frontendDir.Replace("'", "''"))'; & '$($nodeRuntime.Replace("'", "''"))' '$($nextEntry.Replace("'", "''"))' start"

Write-Host "Starting backend at http://localhost:8000 ..." -ForegroundColor Green
Start-Process powershell.exe -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $backendCommand
)

Write-Host "Starting website at http://localhost:3000 ..." -ForegroundColor Green
Start-Process powershell.exe -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $frontendCommand
)

if (-not $SkipBrowser) {
    Start-Sleep -Seconds 4
    Start-Process "http://localhost:3000"
}

Write-Host ""
Write-Host "Fourth Down is starting." -ForegroundColor Green
Write-Host "Keep the two server windows open while using the site." -ForegroundColor Gray
Write-Host "Close those windows when you are finished." -ForegroundColor Gray
Write-Host ""
