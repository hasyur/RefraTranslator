param(
    [switch]$WithOcr,
    [switch]$WithGui
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pipCache = Join-Path $projectRoot ".cache\pip"

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $projectRoot ".venv")
}

$extras = @("dev")
if ($WithOcr) { $extras += "ocr" }
if ($WithGui) { $extras += "gui" }
$installTarget = ".[" + ($extras -join ",") + "]"

$env:PIP_REQUIRE_VIRTUALENV = "true"
& $venvPython -m pip install --cache-dir $pipCache --upgrade pip
& $venvPython -m pip install --cache-dir $pipCache --editable $installTarget

Write-Host "隔离环境已就绪：$venvPython"
Write-Host "验证命令：& '$venvPython' -m pytest"
