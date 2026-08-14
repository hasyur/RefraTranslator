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
    throw "-WithOcr（CPU）和 -WithGpuOcr（GPU）不能同时使用"
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
        throw "无法读取${Context}的 Python 版本：$PythonPath"
    }
    try {
        $version = [version]$versionText.Trim()
    }
    catch {
        throw "无法解析${Context}的 Python 版本：$versionText"
    }
    if ($version -lt [version]"3.11" -or $version -ge [version]"3.14") {
        throw "${Context}使用 Python $version；RefraTranslator 需要 Python 3.11、3.12 或 3.13"
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $systemPython) {
        throw "找不到 Python。请先安装 64 位 Python 3.11、3.12 或 3.13，并勾选 Add Python to PATH"
    }
    Assert-SupportedPython -PythonPath $systemPython.Source -Context "系统"
    & $systemPython.Source -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "创建项目虚拟环境失败" }
}
Assert-SupportedPython -PythonPath $venvPython -Context "项目虚拟环境"

function Invoke-VenvPython {
    & $venvPython @args
    if ($LASTEXITCODE -ne 0) {
        throw "项目虚拟环境命令失败：$($args -join ' ')"
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
    if ($gpuWheels.Count -eq 0) { throw "GPU Paddle wheel 下载后未找到" }
    $gpuWheelPath = $gpuWheels[0].FullName
    Invoke-VenvPython -m pip uninstall --yes paddlepaddle
    Invoke-VenvPython -m pip install --cache-dir $pipCache $gpuWheelPath
}
Invoke-VenvPython -m pip install --cache-dir $pipCache --editable $installTarget

if (-not (Test-Path -LiteralPath $localConfig)) {
    if (-not (Test-Path -LiteralPath $configTemplate)) {
        throw "找不到公开配置模板：$configTemplate"
    }
    Copy-Item -LiteralPath $configTemplate -Destination $localConfig
    Write-Host "已创建本机配置：$localConfig"
}
else {
    Write-Host "保留现有本机配置：$localConfig"
}

Write-Host "隔离环境已就绪：$venvPython"
Write-Host "启动方式：双击 start_gui.bat"
if ($WithDev) {
    Write-Host "验证命令：& '$venvPython' -m pytest"
}
