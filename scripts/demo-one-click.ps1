param(
    [switch]$NoBrowser,
    [ValidateRange(2,20)][int]$Datasets = 20,
    [string]$OutputRoot
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
if (-not $OutputRoot) { $OutputRoot = Join-Path $repo '.local/demo-runs' }
$runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6)
$runPath = Join-Path ([IO.Path]::GetFullPath($OutputRoot)) $runName
New-Item -ItemType Directory -Path $runPath -Force | Out-Null
$python = Join-Path $repo '.venv/Scripts/python.exe'

try {
    Write-Host ''
    Write-Host 'PRISM - One-click local demonstration' -ForegroundColor Cyan
    Write-Host 'Synthetic data only. Approvals in this automated rehearsal are simulated.'
    Write-Host ''
    Write-Host '[1/4] Starting and verifying MySQL, local GPU inference and PRISM...'
    & (Join-Path $PSScriptRoot 'start-local.ps1') -NoBrowser *>&1 | Out-File -LiteralPath (Join-Path $runPath 'startup.log') -Encoding utf8
    Write-Host '[2/4] Running fresh-source recommendations, simulated approvals and learning replay...'
    $arguments = @('-m','scripts.demo_local_pipeline','--mysql','--model-batches','2','--batches',[string]$Datasets,'--output',('"'+$runPath+'"'))
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runPath 'pipeline.log') -RedirectStandardError (Join-Path $runPath 'pipeline-errors.log')
    $null = $process.Handle
    while (-not $process.WaitForExit(1000)) {
        $count = 0
        $summaryPath = Join-Path $runPath 'summary.json'
        if (Test-Path -LiteralPath $summaryPath) {
            try { $completed = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json; $count = $completed.Count } catch { }
        }
        Write-Progress -Activity 'PRISM migration demonstration' -Status ("$count of $Datasets datasets complete") -PercentComplete ([Math]::Min(99,100*$count/$Datasets))
    }
    $process.WaitForExit()
    Write-Progress -Activity 'PRISM migration demonstration' -Completed
    if ($process.ExitCode -ne 0) { throw 'Pipeline failed. Read pipeline-errors.log in this run folder.' }
    Write-Host '[3/4] Checking evidence and generating the offline results report...'
    & $python -m scripts.demo_report --run $runPath
    if ($LASTEXITCODE -ne 0) { throw 'Report validation failed.' }
    $report = Join-Path $runPath 'PRISM Demo Report.html'
    $summaries = Get-Content -LiteralPath (Join-Path $runPath 'summary.json') -Raw | ConvertFrom-Json
    $samples = Join-Path $runPath 'SQL Source Samples'
    & $python -m scripts.export_erp_samples --output $samples
    if ($LASTEXITCODE -ne 0) { throw 'SQL sample export failed.' }
    $qlikFolder = Join-Path $runPath 'Qlik Demo'
    & $python -m scripts.prepare_qlik_demo --run $runPath --output $qlikFolder
    if ($LASTEXITCODE -ne 0) { throw 'Qlik file preparation failed.' }
    # The core demo also works when Qlik is absent or its session is not launched.
    $qlikSocket = New-Object Net.Sockets.TcpClient
    try {
        $qlikSocket.Connect('127.0.0.1',4848)
        & $python -m scripts.load_qlik_demo --folder $qlikFolder 2>&1 | Out-File -LiteralPath (Join-Path $runPath 'qlik-load.log') -Encoding utf8
        if ($LASTEXITCODE -ne 0) { Write-Host 'Qlik files prepared; desktop load pending. See qlik-load.log.' -ForegroundColor Yellow }
        else { Write-Host ('Qlik Desktop app loaded. URL recorded in '+(Join-Path $qlikFolder 'qlik-app.json')) }
    } catch { Write-Host 'Qlik files prepared. Launch Qlik Desktop to load them.' }
    finally { $qlikSocket.Dispose() }
    $latest = @{run=$runPath;report=$report;datasets=$summaries.Count;completed=(Get-Date).ToString('o');synthetic=$true;approval='simulated';samples=$samples}
    $latest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $repo '.local/latest-demo.json') -Encoding utf8
    Write-Host '[4/4] Demo ready.' -ForegroundColor Green
    Write-Host ('First source: '+$summaries[0].before+' findings -> '+$summaries[0].after+' findings')
    Write-Host ('Report: '+$report)
    Write-Host ('SQL / SQLite source samples: '+$samples)
    if (-not $NoBrowser) { Start-Process -FilePath $report }
} catch {
    $_ | Out-String | Out-File -LiteralPath (Join-Path $runPath 'failure.log') -Encoding utf8
    Write-Host ('Demo stopped: '+$_.Exception.Message) -ForegroundColor Red
    Write-Host ('Logs and any partial evidence are preserved in '+$runPath)
    exit 1
}
