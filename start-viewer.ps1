[CmdletBinding()]
param(
    [int]$Port = 8765,
    [string]$VideoPath = "",
    [switch]$NoOpen,
    [switch]$DataOnly,
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$sourceRoot = Join-Path $repoRoot "src"
$appRoot = Join-Path $repoRoot "app"

function Find-Python {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Python was not found. Install Python 3.11 or newer and add it to PATH."
    }

    & $command.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 or newer is required."
    }
    return $command.Source
}

function Find-Video {
    param([string]$ExplicitPath)

    $candidates = @()
    if ($ExplicitPath) {
        $candidates += $ExplicitPath
    }
    if ($env:FLIGHT13_VIEWER_VIDEO_PATH) {
        $candidates += $env:FLIGHT13_VIEWER_VIDEO_PATH
    }
    $candidates += @(
        (Join-Path $repoRoot "media\Flight13_web_720p.mp4"),
        (Join-Path $repoRoot "media\Flight13_launch_to_splashdown_1080p.mp4"),
        (Join-Path (Split-Path $repoRoot -Parent) "data_raw\flight13\Flight13_launch_to_splashdown_1080p.mp4")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

try {
    $python = Find-Python
    if (-not (Test-Path -LiteralPath (Join-Path $appRoot "index.html") -PathType Leaf)) {
        throw "app\index.html is missing. Run this launcher from the repository root."
    }

    $resolvedVideo = if ($DataOnly) { $null } else { Find-Video -ExplicitPath $VideoPath }
    if (-not $resolvedVideo) {
        $DataOnly = $true
    }

    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = if ($oldPythonPath) { "$sourceRoot;$oldPythonPath" } else { $sourceRoot }

    $serverArgs = @(
        "-m", "flight13_viewer",
        "--app-dir", $appRoot,
        "--host", "127.0.0.1",
        "--port", $Port
    )
    if ($resolvedVideo) {
        $serverArgs += @("--video-path", $resolvedVideo)
    } else {
        $serverArgs += @(
            "--video-path", (Join-Path $repoRoot "media\__not_mounted__.mp4"),
            "--allow-missing-video"
        )
    }

    $hudArchive = Join-Path $repoRoot "runtime\source-hud.zip"
    if (Test-Path -LiteralPath $hudArchive -PathType Leaf) {
        $serverArgs += @("--source-hud-archive", $hudArchive)
    }
    if ($NoOpen) {
        $serverArgs += "--no-open"
    }

    Write-Host "Flight 13 local startup check passed." -ForegroundColor Green
    Write-Host "Python: $python"
    Write-Host "App:    $appRoot"
    Write-Host "Video:  $(if ($resolvedVideo) { $resolvedVideo } else { 'not loaded (data-only mode)' })"
    Write-Host "URL:    http://127.0.0.1:$Port/"

    if ($Check) {
        exit 0
    }

    & $python @serverArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "Startup failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
