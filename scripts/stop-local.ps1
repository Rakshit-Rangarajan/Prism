$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
foreach ($name in @('app','slm')) {
    $pidFile=Join-Path $repo ('.local/'+$name+'.pid')
    if (Test-Path -LiteralPath $pidFile) {
        $savedPid=[int](Get-Content -LiteralPath $pidFile)
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid"
        if ($process -and (($name -eq 'app' -and $process.CommandLine -match 'uvicorn app.server:app') -or ($name -eq 'slm' -and $process.Name -eq 'llama-server.exe' -and $process.CommandLine -match '8092'))) {
            Stop-Process -Id $savedPid
        }
        Remove-Item -LiteralPath $pidFile
    }
}
Write-Host 'Stopped PRISM-owned app/model processes. MySQL and all demo data remain available.'
