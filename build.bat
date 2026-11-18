@echo off
rem Gera dist\Daily.exe (um arquivo só, roda sem Python instalado).
setlocal
cd /d "%~dp0"

if not exist ".venv-build\Scripts\python.exe" (
    echo Criando ambiente de build...
    python -m venv .venv-build || goto erro
)
set PY=.venv-build\Scripts\python.exe

echo Instalando PyInstaller e Pillow...
%PY% -m pip install -q --upgrade pip pyinstaller pillow tzdata || goto erro

echo Gerando icone...
%PY% gerar_icone.py || goto erro

echo Empacotando...
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Daily --icon daily.ico --exclude-module PIL ^
    --hidden-import tzdata --collect-data tzdata daily.pyw || goto erro

echo.
echo Pronto: %~dp0dist\Daily.exe
goto fim

:erro
echo.
echo Falhou. Veja as mensagens acima.
exit /b 1

:fim
endlocal
