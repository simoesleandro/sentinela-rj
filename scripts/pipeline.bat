@echo off
cd /d C:\Users\Leand\OneDrive\Desktop\Sentinela
if not exist logs mkdir logs
set LOGFILE=logs\pipeline_%date:~6,4%%date:~3,2%%date:~0,2%.txt
echo ========================================= >> %LOGFILE%
echo PIPELINE INICIADO: %date% %time% >> %LOGFILE%
echo ========================================= >> %LOGFILE%
C:\Users\Leand\AppData\Local\Programs\Python\Python313\python.exe -m automacoes.pipeline --once >> %LOGFILE% 2>&1
set RC=%ERRORLEVEL%
echo. >> %LOGFILE%
echo PIPELINE CONCLUIDO (exit=%RC%): %date% %time% >> %LOGFILE%
exit /b %RC%
