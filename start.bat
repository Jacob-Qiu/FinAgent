@echo off
echo ========================================
echo Starting FinAgent Services
echo ========================================
echo.

echo [1/2] Starting FinanceMCP Server...
start "FinanceMCP Server" cmd /k "npx -y finance-mcp-http"
echo FinanceMCP Server is starting in a new window...
echo Waiting 5 seconds for server initialization...
timeout /t 5 /nobreak >nul
echo.

echo [2/2] Starting FinAgent...
echo.
uv run python agent.py

echo.
echo ========================================
echo FinAgent has stopped.
echo ========================================
pause
