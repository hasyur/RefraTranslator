$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$bootstrapPath = Join-Path $projectRoot "bootstrap.ps1"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$gitCommand = Get-Command git -ErrorAction SilentlyContinue

if ($null -eq $gitCommand) {
    throw (
        "Git was not found. update.bat requires a Git clone, not a GitHub ZIP. " +
        "Install Git, clone RefraTranslator once into a short path such as " +
        "C:\RefraTranslator, then use update.bat for later updates."
    )
}

function Invoke-ProjectGit {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs
    )

    & $gitCommand.Source -C $projectRoot @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($GitArgs -join ' ')"
    }
}

$insideWorkTree = & $gitCommand.Source -C $projectRoot `
    rev-parse --is-inside-work-tree 2>$null
if ($LASTEXITCODE -ne 0 -or $insideWorkTree.Trim() -ne "true") {
    throw (
        "This folder is not a Git clone. GitHub ZIP downloads cannot be " +
        "updated incrementally. Clone RefraTranslator once, run install.bat, " +
        "then keep that folder for future updates."
    )
}

$currentBranch = (
    Invoke-ProjectGit -GitArgs @("branch", "--show-current")
).Trim()
if ([string]::IsNullOrWhiteSpace($currentBranch)) {
    throw "The repository is in detached HEAD state. Switch to main before updating."
}
if ($currentBranch -ne "main") {
    throw "update.bat only updates main; the current branch is '$currentBranch'."
}

$trackedChanges = @(
    Invoke-ProjectGit -GitArgs @(
        "status",
        "--porcelain",
        "--untracked-files=no"
    )
)
if ($trackedChanges.Count -gt 0) {
    Write-Host "Tracked source changes were found:"
    $trackedChanges | ForEach-Object { Write-Host "  $_" }
    throw (
        "Update stopped to avoid overwriting source changes. Commit or restore " +
        "them first. Local config.toml, profiles, caches, logs, and .venv are ignored."
    )
}

$oldCommit = (
    Invoke-ProjectGit -GitArgs @("rev-parse", "HEAD")
).Trim()
Write-Host "Current version: $($oldCommit.Substring(0, 8))"
Write-Host "Checking GitHub main for updates..."
Invoke-ProjectGit -GitArgs @("pull", "--ff-only", "origin", "main")
$newCommit = (
    Invoke-ProjectGit -GitArgs @("rev-parse", "HEAD")
).Trim()

$sourceChanged = $oldCommit -ne $newCommit
$dependencyChanged = $false
if ($sourceChanged) {
    Write-Host "Updated source: $($oldCommit.Substring(0, 8)) -> $($newCommit.Substring(0, 8))"
    & $gitCommand.Source -C $projectRoot diff --quiet `
        $oldCommit $newCommit -- pyproject.toml
    $dependencyDiffExit = $LASTEXITCODE
    if ($dependencyDiffExit -eq 1) {
        $dependencyChanged = $true
    }
    elseif ($dependencyDiffExit -ne 0) {
        throw "Could not determine whether Python dependencies changed."
    }
}
else {
    Write-Host "RefraTranslator is already up to date."
}

$environmentMissing = -not (Test-Path -LiteralPath $venvPython)
if ($environmentMissing -or $dependencyChanged) {
    if (-not (Test-Path -LiteralPath $bootstrapPath)) {
        throw "Updated bootstrap script was not found: $bootstrapPath"
    }
    if ($environmentMissing) {
        Write-Host "The isolated environment is missing; starting the installer."
    }
    else {
        Write-Host "Python dependency declarations changed; refreshing the isolated environment."
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $bootstrapPath -WithGui
    if ($LASTEXITCODE -ne 0) {
        throw "The isolated environment refresh failed. Run install.bat again."
    }
}
elseif ($sourceChanged) {
    Write-Host "Python dependencies did not change; keeping the existing .venv."
}

Write-Host "Update ready. Double-click start_gui.bat to launch RefraTranslator."
