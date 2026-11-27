param([switch]$NoBrowser, [switch]$AppOnly)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
$settingsPath = Join-Path $repo '.local/settings.json'
if (-not (Test-Path -LiteralPath $settingsPath)) { throw 'Run local setup first; .local/settings.json is missing.' }
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
$python = Join-Path $repo '.venv/Scripts/python.exe'
$env:PRISM_COMPANY_ID = $settings.company
$env:PRISM_COMPANY_ROOT = Join-Path $repo '.local/companies'
$env:PRISM_DB = Join-Path $repo '.local/application.sqlite'
$env:PRISM_ERP_DEMO_DB = Join-Path $repo '.local/legacy-erp.sqlite'
$env:PRISM_SLM_URL = 'http://127.0.0.1:8092/v1'
$env:PRISM_SLM_MODEL = 'qwen3-4b'
$env:PRISM_DEMO_PASSWORD = $settings.demoPassword
$env:PRISM_MYSQL_HOST = '127.0.0.1'
$env:PRISM_MYSQL_PORT = '3307'
$env:PRISM_MYSQL_DATABASE = 'prism_erp'
$env:PRISM_MYSQL_USER = 'prism_reader'
Get-Content -LiteralPath (Join-Path $repo '.local/mysql.env') | ForEach-Object {
    $pair = $_.Split('=',2)
    if ($pair[0] -eq 'MYSQL_PASSWORD') { $env:PRISM_MYSQL_PASSWORD = $pair[1] }
}
podman info --format '{{.Host.Hostname}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { podman machine start podman-machine-default; if ($LASTEXITCODE -ne 0) { throw 'Podman failed to start' } }
$container = podman inspect prism-mysql --format '{{.State.Running}}'
if ($LASTEXITCODE -ne 0) { throw 'Synthetic MySQL container is missing; follow docs/local-demo.md setup.' }
if ($container -ne 'true') { podman start prism-mysql | Out-Null }
if (-not (Test-Path -LiteralPath $settings.modelPath) -or -not (Test-Path -LiteralPath $settings.runtimePath)) { throw 'Model/runtime files are missing; check local settings.' }
$actualHash = (Get-FileHash -LiteralPath $settings.modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $settings.modelSha256) { throw 'Model hash mismatch. Do not launch with unsynchronized model artifacts.' }
function Test-Endpoint($url) { try { $r=Invoke-WebRequest $url -TimeoutSec 3; return $r.StatusCode -eq 200 } catch { return $false } }
if (-not $AppOnly) {
if (-not (Test-Endpoint 'http://127.0.0.1:8092/health')) {
    $modelArgs = @('-m', ('"'+$settings.modelPath+'"'),'--host','127.0.0.1','--port','8092','-ngl','99','-c','4096','--parallel','1','--alias','qwen3-4b','--no-webui')
    if ($settings.adapterPath) {
        if ((Get-FileHash -LiteralPath $settings.adapterPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $settings.adapterSha256) { throw 'Adapter hash mismatch' }
        $modelArgs += @('--lora', ('"'+$settings.adapterPath+'"'))
    }
    $proc=Start-Process -FilePath $settings.runtimePath -ArgumentList $modelArgs -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput '.local/slm.stdout.log' -RedirectStandardError '.local/slm.stderr.log'
    $proc.Id | Set-Content '.local/slm.pid'
    $ready=$false
    for ($i=0; $i -lt 40; $i++) { if (Test-Endpoint 'http://127.0.0.1:8092/health') { $ready=$true; break }; Start-Sleep -Milliseconds 500 }
    if (-not $ready) { throw 'Model did not become ready; see .local/slm.stderr.log' }
}
$models = Invoke-RestMethod 'http://127.0.0.1:8092/v1/models'
if ('qwen3-4b' -notin $models.data.id) { throw 'An unexpected model is serving port 8092' }
}
if (-not (Test-Endpoint 'http://127.0.0.1:8091/api/health')) {
    $proc=Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.server:app','--host','127.0.0.1','--port','8091') -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput '.local/app.stdout.log' -RedirectStandardError '.local/app.stderr.log'
    $proc.Id | Set-Content '.local/app.pid'
    $ready=$false
    for ($i=0; $i -lt 40; $i++) { if (Test-Endpoint 'http://127.0.0.1:8091/api/health') { $ready=$true; break }; Start-Sleep -Milliseconds 500 }
    if (-not $ready) { throw 'PRISM did not become ready; see .local/app.stderr.log' }
}
$credentials = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('prism:'+$settings.demoPassword))
$state = Invoke-RestMethod 'http://127.0.0.1:8091/api/local/status' -Headers @{Authorization=('Basic '+$credentials)}
if ($state.company -ne $settings.company) { throw 'Running PRISM is bound to another company. Stop the previous instance first.' }
if (-not $AppOnly) {
    & $python -m scripts.check_local_demo
    if ($LASTEXITCODE -ne 0) { throw 'Local demo checks failed. See diagnostic output above.' }
}
Write-Host ('PRISM ready: http://127.0.0.1:8091 | Company: '+$state.company+' | Model: '+$state.model)
Write-Host 'Login username: prism. Password is in the private .local/settings.json file.'
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8091' }
