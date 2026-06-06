# Sentinela RJ — Agendamento de tarefas no Windows Task Scheduler
# Execute como Administrador para registrar as tarefas

Write-Host "Registrando tarefas do Sentinela RJ..." -ForegroundColor Cyan

# Tarefa 1 — SentinelaColeta (toda segunda-feira 08:00)
cmd /c 'schtasks /create /tn "SentinelaColeta" /tr "C:\Users\Leand\OneDrive\Desktop\Sentinela\scripts\coletar.bat" /sc WEEKLY /d MON /st 08:00 /ru "LEANDROCASA\Leand" /it /rl LIMITED /f'

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] SentinelaColeta agendada para toda segunda-feira as 08:00" -ForegroundColor Green
} else {
    Write-Host "[ERRO] Falha ao criar SentinelaColeta" -ForegroundColor Red
}

# Tarefa 2 — SentinelaInvestiga (toda segunda-feira 09:00, 1h apos coleta)
cmd /c 'schtasks /create /tn "SentinelaInvestiga" /tr "C:\Users\Leand\OneDrive\Desktop\Sentinela\scripts\investigar.bat" /sc WEEKLY /d MON /st 09:00 /ru "LEANDROCASA\Leand" /it /rl LIMITED /f'

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] SentinelaInvestiga agendada para toda segunda-feira as 09:00" -ForegroundColor Green
} else {
    Write-Host "[ERRO] Falha ao criar SentinelaInvestiga" -ForegroundColor Red
}

Write-Host ""
Write-Host "Tarefas registradas. Para verificar:" -ForegroundColor Cyan
Write-Host "  schtasks /query /tn SentinelaColeta /fo LIST"
Write-Host "  schtasks /query /tn SentinelaInvestiga /fo LIST"
