$ErrorActionPreference = 'Stop'

$wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wslCommand) {
    throw 'WSL is required for the local Docker test environment.'
}

$linuxRepoOutput = & wsl.exe --exec wslpath -a $PSScriptRoot
if ($LASTEXITCODE -ne 0 -or $null -eq $linuxRepoOutput) {
    throw 'Could not map this repository path into WSL.'
}
$linuxRepo = ([string]$linuxRepoOutput).Trim()
if (-not $linuxRepo) {
    throw 'Could not map this repository path into WSL.'
}

& wsl.exe --cd $linuxRepo -- docker compose up --build -d --wait
if ($LASTEXITCODE -ne 0) {
    throw 'The local test stack did not become healthy. Inspect it with: docker compose logs ccrate-local-test'
}

$logDirectory = Join-Path $PSScriptRoot 'work\local-validation'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$watcherOutput = Join-Path $logDirectory 'compose-watch.stdout.log'
$watcherError = Join-Path $logDirectory 'compose-watch.stderr.log'
$quotedRepo = '"' + $linuxRepo.Replace('"', '\"') + '"'
$watcherArguments = "--cd $quotedRepo -- flock -n -E 200 /tmp/ccrate-local-test-compose-watch.lock docker compose up --no-build"
$watcher = Start-Process -FilePath $wslCommand.Source -ArgumentList $watcherArguments `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $watcherOutput -RedirectStandardError $watcherError
Start-Sleep -Milliseconds 500
$watcher.Refresh()
if ($watcher.HasExited -and $watcher.ExitCode -ne 200 -and $watcher.ExitCode -ne 0) {
    throw "The WSL Docker keepalive failed. Inspect $watcherError"
}

Write-Host 'C-Crate local test is ready at http://localhost:17745'
Write-Host 'Equipment Terminal: http://localhost:17749'
Write-Host "Read the private local sign-in with: wsl.exe --cd '$linuxRepo' -- docker compose exec ccrate-local-test cat /data/work/baseline/test-account.json"
