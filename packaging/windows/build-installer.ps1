param(
    [string]$Python = "python",
    [switch]$SkipFrontendBuild,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$FrontendDir = Join-Path $ProjectRoot "frontend"
$FrontendDist = Join-Path $FrontendDir "dist"
$SpecPath = Join-Path $ScriptDir "TokenMind.spec"
$IssPath = Join-Path $ScriptDir "TokenMind.iss"
$DistDir = Join-Path $ProjectRoot "dist-windows"
$WorkDir = Join-Path $ProjectRoot "build-windows"
$InstallerDir = Join-Path $ProjectRoot "dist-installer"

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host "==> $Title" -ForegroundColor Cyan
    & $Action
}

function Get-ProjectVersion {
    $Pyproject = Get-Content (Join-Path $ProjectRoot "pyproject.toml") -Raw
    if ($Pyproject -match '(?m)^version\s*=\s*"([^"]+)"') {
        return $Matches[1]
    }
    return "0.0.0"
}

function Get-InnoCompiler {
    $Command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $DefaultPaths = @(
        "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($Path in $DefaultPaths) {
        if ($Path -and (Test-Path $Path)) {
            return $Path
        }
    }
    return $null
}

$Version = Get-ProjectVersion

# Default PyInstaller invocation: python -m PyInstaller
Invoke-Step "Checking Python and PyInstaller" {
    & $Python -m PyInstaller --version | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'PyInstaller is not installed. Run: python -m pip install ".[windows]"'
    }
}

if (-not $SkipFrontendBuild) {
    Invoke-Step "Building frontend" {
        Push-Location $FrontendDir
        try {
            if (-not (Test-Path "node_modules")) {
                if (Test-Path "package-lock.json") {
                    npm ci
                } else {
                    npm install
                }
            }
            npm run build
        } finally {
            Pop-Location
        }
    }
}

if (-not (Test-Path (Join-Path $FrontendDist "index.html"))) {
    throw "frontend/dist/index.html was not found. Build the frontend before packaging."
}

Invoke-Step "Building PyInstaller onedir app" {
    if (Test-Path $DistDir) {
        Remove-Item $DistDir -Recurse -Force
    }
    if (Test-Path $WorkDir) {
        Remove-Item $WorkDir -Recurse -Force
    }
    & $Python -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $WorkDir $SpecPath
}

if ($SkipInstaller) {
    Write-Host ""
    Write-Host "PyInstaller build complete: $DistDir\TokenMind\TokenMind.exe" -ForegroundColor Green
    exit 0
}

$InnoCompiler = Get-InnoCompiler
if (-not $InnoCompiler) {
    throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php or rerun with -SkipInstaller."
}

Invoke-Step "Building Inno Setup installer" {
    if (-not (Test-Path $InstallerDir)) {
        New-Item -ItemType Directory -Path $InstallerDir | Out-Null
    }
    & $InnoCompiler "/DMyAppVersion=$Version" $IssPath
}

Write-Host ""
Write-Host "Installer ready: $InstallerDir\TokenMindSetup-$Version.exe" -ForegroundColor Green
