<#
Registra a tarefa "GestaoUsuarios-Vigia": ao fazer logon, mantem `python -m gestao_usuarios vigiar` rodando (janela oculta).
  .\scripts\agendar_vigia.ps1                                 # dry-run (padrao): analisa e ENSAIA a request, nunca clica em Submit
  .\scripts\agendar_vigia.ps1 -Executar                       # cria as requests de criacao (so depois do 1o caso real acompanhado)
  .\scripts\agendar_vigia.ps1 -Python C:\caminho\python.exe   # outro python (com pyyaml, pywin32, playwright, pillow)
  .\scripts\agendar_vigia.ps1 -Remover
Roda SOMENTE com o usuario logado e a tela desbloqueada (SAP GUI Scripting). Sem resposta nova a vigia nao abre SAP nem
navegador. Se cair, o Agendador reinicia (ate 5 vezes, de 2 em 2 min). Uma instancia so (trava em logs\vigia.lock).
Logs: logs\AAAA-MM-DD.log e logs\vigia_console.log.
#>
param(
    [string]$Python = "",
    [switch]$Executar,
    [switch]$Remover
)
$nome = "GestaoUsuarios-Vigia"
if ($Remover) {
    Stop-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $nome -Confirm:$false -ErrorAction Stop
    Write-Host "Tarefa removida."
    return
}
$raiz = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $raiz ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { throw "Python nao encontrado: $Python (use -Python)" }
$vbs = Join-Path $raiz "scripts\rodar_vigia.vbs"
$argumento = "//B //Nologo `"$vbs`" `"$Python`""
if ($Executar) { $argumento += " --executar" }
$acao = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $argumento -WorkingDirectory $raiz
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$gatilho = New-ScheduledTaskTrigger -AtLogOn -User $usuario
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 2) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $config -Principal $principal -Force | Out-Null
$modo = if ($Executar) { "EXECUTAR (cria requests)" } else { "DRY-RUN (ensaia, sem Submit)" }
Write-Host "Tarefa '$nome' registrada: ao fazer logon, modo $modo, python $Python."
