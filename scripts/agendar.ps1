# Sentinela RJ — Agendamento de tarefas no Windows Task Scheduler
# Execute como Administrador para registrar as tarefas

$ProjectRoot = "C:\Users\Leand\OneDrive\Desktop\Sentinela"
$PipelineBat = Join-Path $ProjectRoot "scripts\pipeline.bat"
$RunAs = "LEANDROCASA\Leand"

Write-Host "Registrando tarefas do Sentinela RJ..." -ForegroundColor Cyan

# Tarefa unica — SentinelaPipeline (toda segunda-feira 08:00)
cmd /c "schtasks /create /tn `"SentinelaPipeline`" /tr `"$PipelineBat`" /sc WEEKLY /d MON /st 08:00 /ru `"$RunAs`" /it /rl LIMITED /f"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] SentinelaPipeline agendada para toda segunda-feira as 08:00" -ForegroundColor Green
    Write-Host "     Esteira: coletar -> enriquecer -> analisar -> investigar -> Discord" -ForegroundColor DarkGray
} else {
    Write-Host "[ERRO] Falha ao criar SentinelaPipeline" -ForegroundColor Red
}

Write-Host ""
Write-Host "Tarefas legadas (opcional — desativar se usar SentinelaPipeline):" -ForegroundColor Yellow
Write-Host "  schtasks /delete /tn SentinelaColeta /f"
Write-Host "  schtasks /delete /tn SentinelaInvestiga /f"
Write-Host ""
Write-Host "Verificar:" -ForegroundColor Cyan
Write-Host "  schtasks /query /tn SentinelaPipeline /fo LIST"
Write-Host "  type $ProjectRoot\logs\pipeline_*.txt"
