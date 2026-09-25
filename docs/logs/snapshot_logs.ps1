<#
Dumps the full stdout log history of every environment container to a
timestamped folder under docs/logs/, so they survive even if a container
later gets removed or recreated (docker logs only works while the
container itself still exists).

Usage: run from anywhere, e.g.
    .\docs\logs\snapshot_logs.ps1
#>

$ErrorActionPreference = "Continue"

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$outDir = Join-Path $PSScriptRoot $timestamp
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$containers = @(
    "RedMap",
    "identity-event-source",
    "ics-event-source",
    "cloud-target-lab"
)

foreach ($name in $containers) {
    $exists = docker ps -a --format "{{.Names}}" | Select-String -SimpleMatch $name
    if (-not $exists) {
        Write-Host "Skipping '$name' - container not found (docker ps -a)"
        continue
    }

    $outFile = Join-Path $outDir "$name.log"
    docker logs $name *> $outFile
    Write-Host "Saved $name -> $outFile"
}

Write-Host "`nSnapshot complete: $outDir"
