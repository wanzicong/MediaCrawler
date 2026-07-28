[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $ProjectRoot "data\runtime"
$StateFile = Join-Path $RuntimeDir "mcp_server.json"
$ExpectedPythonRoot = (Join-Path $ProjectRoot ".venv\").ToLowerInvariant()
$script:StoppedIds = [System.Collections.Generic.List[int]]::new()
$script:VisitedIds = [System.Collections.Generic.HashSet[int]]::new()

function Test-IsProjectMcpProcess {
    param($ProcessInfo)

    if (-not $ProcessInfo) {
        return $false
    }
    $executablePath = [string]$ProcessInfo.ExecutablePath
    $commandLine = [string]$ProcessInfo.CommandLine
    return (
        $executablePath.ToLowerInvariant().StartsWith($ExpectedPythonRoot) -and
        $commandLine -match "(^|\s)-m\s+mcp_server(\s|$)"
    )
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    if (-not $script:VisitedIds.Add($ProcessId)) {
        return
    }
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        $script:StoppedIds.Add($ProcessId)
    }
}

$seedIds = [System.Collections.Generic.HashSet[int]]::new()
if (Test-Path -LiteralPath $StateFile -PathType Leaf) {
    try {
        $state = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $stateProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$state.pid)" -ErrorAction SilentlyContinue
        if (Test-IsProjectMcpProcess -ProcessInfo $stateProcess) {
            [void]$seedIds.Add([int]$state.pid)
        }
    }
    catch {
        Write-Warning "MCP state file could not be read; falling back to process discovery: $($_.Exception.Message)"
    }
}

if ($seedIds.Count -eq 0) {
    $projectProcesses = Get-CimInstance Win32_Process | Where-Object {
        Test-IsProjectMcpProcess -ProcessInfo $_
    }
    foreach ($process in $projectProcesses) {
        [void]$seedIds.Add([int]$process.ProcessId)
    }
}

if ($seedIds.Count -eq 0) {
    Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
    Write-Host "MCP server is not running."
    exit 0
}

foreach ($processIdValue in $seedIds) {
    Stop-ProcessTree -ProcessId $processIdValue
}

$deadline = (Get-Date).AddSeconds(10)
do {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $listener) {
        break
    }
    Start-Sleep -Milliseconds 200
} while ((Get-Date) -lt $deadline)

Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue

if ($listener) {
    throw "MCP process stopped, but port $Port is still used by PID=$($listener.OwningProcess)."
}

$stoppedText = ($script:StoppedIds | Sort-Object -Unique) -join ", "
Write-Host "MCP server stopped. PID: $stoppedText"
