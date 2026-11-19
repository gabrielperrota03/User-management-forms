<#
Registra a tarefa "GestaoUsuarios-Lista-ZBR" no Agendador de Tarefas (usuario atual, sem admin).
  .\scripts\agendar_zbr.ps1                                  # segundas as 08:00, python do .venv do repositorio
  .\scripts\agendar_zbr.ps1 -Python C:\caminho\python.exe    # outro python (com pyyaml e pywin32)
  .\scripts\agendar_zbr.ps1 -Dia Tuesday -Hora 07:30
  .\scripts\agendar_zbr.ps1 -Remover
Roda SOMENTE com o usuario logado (o SAP GUI Scripting precisa de sessao interativa e tela desbloqueada).
Se o PC estiver desligado no horario, roda assim que possivel (StartWhenAvailable). Log em logs\tarefa_zbr.log.
#>
param(
    [string]$Dia = "Monday",
    [string]$Hora = "08:00",
    [string]$Python = "",
    [switch]$Remover
)
$nome = "GestaoUsuarios-Lista-ZBR"
if ($Remover) {
    Unregister-ScheduledTask -TaskName $nome -Confirm:$false -ErrorAction Stop
    Write-Host "Tarefa removida."
    return
}
$raiz = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $raiz ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { throw "Python nao encontrado: $Python (use -Python)" }
$acao = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"`"$raiz\scripts\rodar_zbr.cmd`" `"$Python`"`"" -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Dia -At $Hora
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $config -Principal $principal -Force | Out-Null
Write-Host "Tarefa '$nome' registrada: $Dia as $Hora, python $Python."
