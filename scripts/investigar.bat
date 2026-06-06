@echo off
cd /d C:\Users\Leand\OneDrive\Desktop\Sentinela
if not exist logs mkdir logs
set LOGFILE=logs\pipeline_%date:~6,4%%date:~3,2%%date:~0,2%.txt
echo. >> %LOGFILE%
echo INVESTIGACAO INICIADA: %date% %time% >> %LOGFILE%
C:\Users\Leand\AppData\Local\Programs\Python\Python313\python.exe __main__.py investigar >> %LOGFILE% 2>&1
echo INVESTIGACAO CONCLUIDA: %date% %time% >> %LOGFILE%
