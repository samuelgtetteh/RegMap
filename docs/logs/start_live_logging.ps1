<#
Continuously tails every environment container and appends new output to
a per-container file in real time, for as long as this stays running -
unlike snapshot_logs.ps1 (one-time dump of history so far), this captures
everything that happens *from now on* as it happens.

Usage:
    .\docs\logs\start_live_logging.ps1
    (leave the window open / running in the background)

    Ctrl+C to stop. Or close the window - it doesn't touch the containers
    themselves, only reads their logs.
#>

$ErrorActionPreference = "Continue"

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$outDir = Join-Path $PSScriptRoot "live_$timestamp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$containers = @(
    "RedMap",
    "identity-event-source",
    "ics-event-source",
    "cloud-target-lab"
)

$jobs = @()

foreach ($name in $containers) {
    $exists = docker ps -a --format "{{.Names}}" | Select-String -SimpleMatch $name
    if (-not $exists) {
        Write-Host "Skipping '$name' - container not found (docker ps -a)"
        continue
    }

    $outFile = Join-Path $outDir "$name.log"
    Write-Host "Following $name -> $outFile"

    # -f prints full existing history first, then keeps following new output.
    $job = Start-Job -ScriptBlock {
        param($containerName, $file)
        docker logs -f $containerName *>> $file
    } -ArgumentList $name, $outFile

    $jobs += $job
}

Write-Host "`nLive logging started -> $outDir"
Write-Host "Following $($jobs.Count) container(s). Press Ctrl+C to stop."

try {
    while ($true) {
        Start-Sleep -Seconds 2
    }
}
finally {
    Write-Host "`nStopping..."
    $jobs | Stop-Job
    $jobs | Remove-Job
    Write-Host "Stopped. Logs saved under $outDir"
}
