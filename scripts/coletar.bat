@echo off
cd /d C:\Users\Leand\OneDrive\Desktop\Sentinela
if not exist logs mkdir logs
set LOGFILE=logs\pipeline_%date:~6,4%%date:~3,2%%date:~0,2%.txt
echo ========================================= >> %LOGFILE%
echo COLETA INICIADA: %date% %time% >> %LOGFILE%
echo ========================================= >> %LOGFILE%
C:\Users\Leand\AppData\Local\Programs\Python\Python313\python.exe __main__.py coletar >> %LOGFILE% 2>&1
echo. >> %LOGFILE%
echo ANALISE INICIADA: %date% %time% >> %LOGFILE%
C:\Users\Leand\AppData\Local\Programs\Python\Python313\python.exe __main__.py analisar >> %LOGFILE% 2>&1
echo. >> %LOGFILE%
echo PIPELINE CONCLUIDO: %date% %time% >> %LOGFILE%
