# Script de Agendamento Limpo - Sentinela Pipeline
$TaskName = "SentinelaPipeline"
$BatPath = "C:\Users\Leand\OneDrive\Desktop\Sentinela\scripts\pipeline.bat"

Write-Host "Registering Windows Task: $TaskName..." -ForegroundColor Cyan

# Remove a tarefa antiga se ela ja existir para evitar conflito
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Configura a acao para rodar o nosso arquivo .bat centralizado
$Action = New-ScheduledTaskAction -Execute $BatPath

# Configura o disparador para Toda Segunda-Feira as 08:00
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 08:00

# Configura as definicoes para permitir execucao sob demanda e em background
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Registra a tarefa nativamente no Windows
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Pipeline centralizado do Sentinela RJ - Coleta, Analise, IA e Discord"

Write-Host "Success! Task $TaskName registered successfully to run every Monday at 08:00." -ForegroundColor Green