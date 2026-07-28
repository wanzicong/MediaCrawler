[CmdletBinding()]
param(
    [string]$ListenHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8765,
    [string]$McpPath = "/mcp",
    [string[]]$AllowedHost = @(),
    [string[]]$AllowedOrigin = @()
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RuntimeDir = Join-Path $ProjectRoot "data\runtime"
$StateFile = Join-Path $RuntimeDir "mcp_server.json"
$LogDir = Join-Path $ProjectRoot "logs"
$StdoutLog = Join-Path $LogDir "mcp_server.stdout.log"
$StderrLog = Join-Path $LogDir "mcp_server.stderr.log"

function Get-McpProcess {
    param([int]$ProcessId)

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }
    $expectedPythonRoot = (Join-Path $ProjectRoot ".venv\").ToLowerInvariant()
    $executablePath = [string]$process.ExecutablePath
    $commandLine = [string]$process.CommandLine
    if (
        $executablePath.ToLowerInvariant().StartsWith($expectedPythonRoot) -and
        $commandLine -match "(^|\s)-m\s+mcp_server(\s|$)"
    ) {
        return $process
    }
    return $null
}

function Get-HealthHost {
    param([string]$Address)

    if ($Address -eq "0.0.0.0") {
        return "127.0.0.1"
    }
    if ($Address -eq "::") {
        return "[::1]"
    }
    if ($Address.Contains(":") -and -not $Address.StartsWith("[")) {
        return "[$Address]"
    }
    return $Address
}

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Project Python environment was not found: $PythonPath. Run 'uv sync' first."
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

if (Test-Path -LiteralPath $StateFile -PathType Leaf) {
    try {
        $state = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $existingProcess = Get-McpProcess -ProcessId ([int]$state.pid)
        if ($existingProcess) {
            Write-Host "MCP server is already running. PID=$($state.pid) URL=$($state.endpoint)"
            exit 0
        }
    }
    catch {
        Write-Warning "Invalid MCP state file; starting a new server: $($_.Exception.Message)"
    }
    Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $ownerDescription = if ($owner) { "$($owner.Name) PID=$($owner.ProcessId)" } else { "PID=$($listener.OwningProcess)" }
    throw "Port $Port is already used by $ownerDescription. MCP server was not started."
}

$arguments = @(
    "-m", "mcp_server",
    "--transport", "streamable-http",
    "--host", $ListenHost,
    "--port", [string]$Port,
    "--path", $McpPath
)
foreach ($value in $AllowedHost) {
    if ($value) {
        $arguments += @("--allowed-host", $value)
    }
}
foreach ($value in $AllowedOrigin) {
    if ($value) {
        $arguments += @("--allowed-origin", $value)
    }
}

$serverProcess = Start-Process `
    -FilePath $PythonPath `
    -ArgumentList $arguments `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -PassThru

$healthHost = Get-HealthHost -Address $ListenHost
$healthUrl = "http://${healthHost}:$Port/health"
$endpoint = "http://${healthHost}:$Port$McpPath"
$deadline = (Get-Date).AddSeconds(20)
$healthy = $false
do {
    if ($serverProcess.HasExited) {
        break
    }
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($health.status -eq "ok") {
            $healthy = $true
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 300
    }
} while ((Get-Date) -lt $deadline)

if (-not $healthy) {
    Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    $errorTail = ""
    if (Test-Path -LiteralPath $StderrLog -PathType Leaf) {
        $errorTail = (Get-Content -LiteralPath $StderrLog -Tail 30 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
    }
    throw "MCP server did not become healthy in 20 seconds. Error log: $StderrLog`n$errorTail"
}

$state = [ordered]@{
    pid = $serverProcess.Id
    host = $ListenHost
    port = $Port
    path = $McpPath
    endpoint = $endpoint
    health_url = $healthUrl
    started_at = (Get-Date).ToString("o")
}
$state | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8

Write-Host "MCP server started successfully."
Write-Host "PID: $($serverProcess.Id)"
Write-Host "MCP: $endpoint"
Write-Host "Health: $healthUrl"
Write-Host "Logs: $StdoutLog / $StderrLog"
