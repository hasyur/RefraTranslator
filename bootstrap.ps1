param(
    [switch]$WithOcr,
    [switch]$WithGpuOcr,
    [ValidateSet("CPU", "NVIDIA", "None")]
    [string]$OcrDevice,
    [ValidateSet("cu118", "cu126", "cu129", "cu130")]
    [string]$GpuCuda = "cu129",
    [switch]$WithGui,
    [switch]$WithDev,
    [switch]$KeepInstallCache
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
if ($PSBoundParameters.ContainsKey("OcrDevice") -and ($WithOcr -or $WithGpuOcr)) {
    throw "-OcrDevice cannot be combined with -WithOcr or -WithGpuOcr"
}

function Read-OcrDeviceChoice {
    Write-Host "Select the PaddleOCR runtime to install:"
    Write-Host "  [1] NVIDIA GPU (default)"
    Write-Host "  [2] CPU"
    while ($true) {
        $choice = Read-Host "OCR device [1]"
        if ([string]::IsNullOrWhiteSpace($choice)) { return "nvidia" }
        switch ($choice.Trim().ToLowerInvariant()) {
            "1" { return "nvidia" }
            "nvidia" { return "nvidia" }
            "gpu" { return "nvidia" }
            "2" { return "cpu" }
            "cpu" { return "cpu" }
            default { Write-Host "Enter 1 for NVIDIA GPU or 2 for CPU." }
        }
    }
}

$ocrInstallDevice = "none"
if ($WithOcr) {
    $ocrInstallDevice = "cpu"
}
elseif ($WithGpuOcr) {
    $ocrInstallDevice = "nvidia"
}
elseif ($PSBoundParameters.ContainsKey("OcrDevice")) {
    $ocrInstallDevice = $OcrDevice.ToLowerInvariant()
}
elseif ($WithGui) {
    $ocrInstallDevice = Read-OcrDeviceChoice
}
$installCpuOcr = $ocrInstallDevice -eq "cpu"
$installGpuOcr = $ocrInstallDevice -eq "nvidia"

switch ($ocrInstallDevice) {
    "nvidia" { Write-Host "OCR installation selected: NVIDIA GPU ($GpuCuda)" }
    "cpu" { Write-Host "OCR installation selected: CPU" }
    default { Write-Host "OCR installation skipped" }
}

function Assert-OcrInstallPathLength {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    # Paddle 3.3 ships deeply nested C++ headers. On Windows installations that
    # still use the traditional MAX_PATH limit, this exact file is the first
    # known path that can fail while pip expands the wheel.
    $paddleDeepPath = Join-Path $ProjectRoot (
        ".venv\Lib\site-packages\paddle\include\paddle\phi\kernels\fusion\" +
        "cutlass\memory_efficient_attention\iterators\" +
        "predicated_tile_access_iterator_residual_last.h"
    )
    if ($paddleDeepPath.Length -le 259) {
        return
    }

    $driveRoot = [System.IO.Path]::GetPathRoot($ProjectRoot)
    $suggestedRoot = Join-Path $driveRoot "RefraTranslator"
    throw (
        "Project path is too long for a reliable PaddleOCR install on Windows. " +
        "The deepest Paddle file would use $($paddleDeepPath.Length) characters " +
        "(safe maximum: 259). Move or extract the project to a shorter path, " +
        "for example '$suggestedRoot'. If an earlier attempt created .venv, " +
        "remove only that partial folder after moving, then rerun bootstrap.ps1."
    )
}

if ($installCpuOcr -or $installGpuOcr) {
    Assert-OcrInstallPathLength -ProjectRoot $projectRoot
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

function Clear-PipInstallCache {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$PipCachePath
    )

    $resolvedProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
    $expectedPipCache = [System.IO.Path]::GetFullPath(
        (Join-Path (Join-Path $resolvedProjectRoot ".cache") "pip")
    )
    $resolvedPipCache = [System.IO.Path]::GetFullPath($PipCachePath)
    if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals(
        $resolvedPipCache,
        $expectedPipCache
    )) {
        throw "Refusing to remove an unexpected pip cache path: $resolvedPipCache"
    }
    if (-not (Test-Path -LiteralPath $resolvedPipCache)) {
        Write-Host "No installer download cache to remove"
        return
    }

    $cacheItem = Get-Item -LiteralPath $resolvedPipCache -Force
    if (($cacheItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to remove a pip cache that is a reparse point: $resolvedPipCache"
    }
    $cacheMeasurement = Get-ChildItem -LiteralPath $resolvedPipCache `
        -Recurse -Force -File -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum
    $cacheSizeBytes = if ($null -eq $cacheMeasurement.Sum) {
        [int64]0
    }
    else {
        [int64]$cacheMeasurement.Sum
    }

    try {
        Remove-Item -LiteralPath $resolvedPipCache -Recurse -Force -ErrorAction Stop
    }
    catch {
        Write-Warning "Could not remove installer download cache: $($_.Exception.Message)"
        Write-Warning "You can remove it later: $resolvedPipCache"
        return
    }

    $releasedLabel = if ($cacheSizeBytes -ge 1GB) {
        "{0:N2} GiB" -f ($cacheSizeBytes / 1GB)
    }
    else {
        "{0:N1} MiB" -f ($cacheSizeBytes / 1MB)
    }
    Write-Host "Removed installer download cache: $resolvedPipCache"
    Write-Host "Released disk space: $releasedLabel"
}

$extras = @()
if ($WithDev) { $extras += "dev" }
if ($installCpuOcr) { $extras += "ocr" }
if ($installGpuOcr) { $extras += "ocr-gpu" }
if ($WithGui) { $extras += "gui" }
$installTarget = $projectRoot
if ($extras.Count -gt 0) {
    $installTarget = "${projectRoot}[$($extras -join ',')]"
}

$env:PIP_REQUIRE_VIRTUALENV = "true"
Invoke-VenvPython -m pip install --cache-dir $pipCache --upgrade pip
if ($installCpuOcr) {
    Invoke-VenvPython -m pip uninstall --yes paddlepaddle-gpu
}
if ($installGpuOcr) {
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
    if ($installGpuOcr) {
        $configText = [System.IO.File]::ReadAllText($localConfig)
        $devicePattern = [regex]'(?m)^device\s*=\s*"cpu"\s*$'
        $updatedConfig = $devicePattern.Replace($configText, 'device = "gpu:0"', 1)
        if ($updatedConfig -eq $configText) {
            throw "Could not set the new configuration to NVIDIA GPU OCR"
        }
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($localConfig, $updatedConfig, $utf8NoBom)
    }
    Write-Host "Created local configuration: $localConfig"
}
else {
    Write-Host "Keeping existing local configuration: $localConfig"
    if ($installGpuOcr) {
        Write-Host "Select gpu:0 in the GUI if this existing configuration still uses CPU OCR"
    }
}

if ($KeepInstallCache) {
    Write-Host "Keeping installer download cache: $pipCache"
}
else {
    Clear-PipInstallCache -ProjectRoot $projectRoot -PipCachePath $pipCache
}

Write-Host "Isolated environment is ready: $venvPython"
Write-Host "Launch by double-clicking start_gui.bat"
if ($WithDev) {
    Write-Host "Test command: & '$venvPython' -m pytest"
}
