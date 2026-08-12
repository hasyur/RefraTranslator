param(
    [switch]$WithOcr,
    [switch]$WithGpuOcr,
    [ValidateSet("cu118", "cu126", "cu129", "cu130")]
    [string]$GpuCuda = "cu129",
    [switch]$WithGui
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pipCache = Join-Path $projectRoot ".cache\pip"

if ($WithOcr -and $WithGpuOcr) {
    throw "-WithOcr（CPU）和 -WithGpuOcr（GPU）不能同时使用"
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "创建项目虚拟环境失败" }
}

function Invoke-VenvPython {
    & $venvPython @args
    if ($LASTEXITCODE -ne 0) {
        throw "项目虚拟环境命令失败：$($args -join ' ')"
    }
}

$extras = @("dev")
if ($WithOcr) { $extras += "ocr" }
if ($WithGpuOcr) { $extras += "ocr-gpu" }
if ($WithGui) { $extras += "gui" }
$installTarget = ".[" + ($extras -join ",") + "]"

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

Write-Host "隔离环境已就绪：$venvPython"
Write-Host "验证命令：& '$venvPython' -m pytest"
