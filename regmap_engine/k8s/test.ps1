# End-to-end test of the engine on Docker Desktop's built-in Kubernetes (PowerShell).
# Prereqs: Docker Desktop > Settings > Kubernetes > Enable Kubernetes (green), and:
#   docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .
$ErrorActionPreference = "Stop"
$ns = "regmap"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path

Write-Host "== context =="; kubectl config current-context
Write-Host "== apply manifests =="
kubectl apply -k "$root\regmap_engine\k8s"
Write-Host "== wait for rollout (model warm-up ~2 min) =="
kubectl -n $ns rollout status deploy/regmap-engine --timeout=210s
kubectl -n $ns get pods -o wide

Write-Host "== port-forward svc/regmap-engine 8010:80 =="
$pf = Start-Process kubectl -ArgumentList "-n",$ns,"port-forward","svc/regmap-engine","8010:80" -PassThru -WindowStyle Hidden
try {
  foreach ($i in 1..20) { try { Invoke-RestMethod localhost:8010/health | Out-Null; break } catch { Start-Sleep 1 } }
  Write-Host "== GET /health =="; Invoke-RestMethod localhost:8010/health | ConvertTo-Json -Depth 5
  Write-Host "== POST /map =="
  $r = Invoke-WebRequest localhost:8010/map -Method Post -ContentType application/json `
        -Body '{"text":"encrypt data at rest","pair":"nist_csf2__nist_80053","top_k":3}'
  Write-Host ("x-regmap-compute-units: " + $r.Headers["x-regmap-compute-units"])
  Write-Host ("x-regmap-device: " + $r.Headers["x-regmap-device"])
  $r.Content
  Write-Host "== GET /usage =="; Invoke-RestMethod localhost:8010/usage | ConvertTo-Json -Depth 5
} finally {
  Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "OK. Tear down with:  kubectl delete -k regmap_engine/k8s"
