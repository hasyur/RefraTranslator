param(
    [switch]$WithOcr,
    [switch]$WithGpuOcr,
    [ValidateSet("cu118", "cu126", "cu129", "cu130")]
    [string]$GpuCuda = "cu129",
    [switch]$WithGui,
    [switch]$WithDev
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pipCache = Join-Path $projectRoot ".cache\pip"
$configTemplate = Join-Path $projectRoot "config.example.toml"
$localConfig = Join-Path $projectRoot "config.toml"

if ($WithOcr -and $WithGpuOcr) {
    throw "-WithOcr (CPU) and -WithGpuOcr (GPU) cannot be used together"
}

function Assert-SupportedPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonPath,
        [Parameter(Mandatory = $true)]
        [string]$Context
    )

    $versionText = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot read the Python version for ${Context}: $PythonPath"
    }
    try {
        $version = [version]$versionText.Trim()
    }
    catch {
        throw "Cannot parse the Python version for ${Context}: $versionText"
    }
    if ($version -lt [version]"3.11" -or $version -ge [version]"3.14") {
        throw "${Context} uses Python $version; RefraTranslator requires Python 3.11, 3.12, or 3.13"
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $systemPython) {
        throw "Python was not found. Install 64-bit Python 3.11, 3.12, or 3.13 and enable Add Python to PATH"
    }
    Assert-SupportedPython -PythonPath $systemPython.Source -Context "System Python"
    & $systemPython.Source -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the project virtual environment" }
}
Assert-SupportedPython -PythonPath $venvPython -Context "Project virtual environment"

function Invoke-VenvPython {
    & $venvPython @args
    if ($LASTEXITCODE -ne 0) {
        throw "Project virtual environment command failed: $($args -join ' ')"
    }
}

$extras = @()
if ($WithDev) { $extras += "dev" }
if ($WithOcr) { $extras += "ocr" }
if ($WithGpuOcr) { $extras += "ocr-gpu" }
if ($WithGui) { $extras += "gui" }
$installTarget = $projectRoot
if ($extras.Count -gt 0) {
    $installTarget = "${projectRoot}[$($extras -join ',')]"
}

$env:PIP_REQUIRE_VIRTUALENV = "true"
Invoke-VenvPython -m pip install --cache-dir $pipCache --upgrade pip
if ($WithOcr) {
    Invoke-VenvPython -m pip uninstall --yes paddlepaddle-gpu
}
if ($WithGpuOcr) {
    $gpuIndex = "https://www.paddlepaddle.org.cn/packages/stable/$GpuCuda/"
    $gpuWheelDir = Join-Path $pipCache "gpu"
    New-Item -ItemType Directory -Force -Path $gpuWheelDir | Out-Null
    Invoke-VenvPython -m pip download --cache-dir $pipCache `
        --no-deps --index-url $gpuIndex --dest $gpuWheelDir `
        "paddlepaddle-gpu==3.3.1"
    $gpuWheels = @(
        Get-ChildItem -LiteralPath $gpuWheelDir -Filter "paddlepaddle_gpu-3.3.1-*.whl" |
            Sort-Object LastWriteTime -Descending
    )
    if ($gpuWheels.Count -eq 0) { throw "The downloaded Paddle GPU wheel was not found" }
    $gpuWheelPath = $gpuWheels[0].FullName
    Invoke-VenvPython -m pip uninstall --yes paddlepaddle
    Invoke-VenvPython -m pip install --cache-dir $pipCache $gpuWheelPath
}
Invoke-VenvPython -m pip install --cache-dir $pipCache --editable $installTarget

if (-not (Test-Path -LiteralPath $localConfig)) {
    if (-not (Test-Path -LiteralPath $configTemplate)) {
        throw "Public configuration template not found: $configTemplate"
    }
    Copy-Item -LiteralPath $configTemplate -Destination $localConfig
    Write-Host "Created local configuration: $localConfig"
}
else {
    Write-Host "Keeping existing local configuration: $localConfig"
}

Write-Host "Isolated environment is ready: $venvPython"
Write-Host "Launch by double-clicking start_gui.bat"
if ($WithDev) {
    Write-Host "Test command: & '$venvPython' -m pytest"
}
