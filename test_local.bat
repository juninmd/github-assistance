@echo off
REM Local Test Script for Development Team Agents (Windows)
REM This script helps you test agents locally before deploying to GitHub Actions

echo =========================================
echo Development Team Agents - Local Test
echo =========================================
echo.

REM Check if .env file exists
if not exist .env (
    echo Error: .env file not found!
    echo.
    echo Create a .env file with the following variables:
    echo.
    echo GITHUB_TOKEN=your_github_token
    echo JULES_API_KEY=your_jules_api_key
    echo GEMINI_API_KEY=your_gemini_api_key
    echo GITHUB_OWNER=juninmd
    echo.
    exit /b 1
)

REM Load environment variables
echo Loading environment variables...
for /f "tokens=*" %%a in (.env) do (
    set %%a
)

REM Verify required variables
if "%GITHUB_TOKEN%"=="" (
    echo Error: GITHUB_TOKEN not set
    exit /b 1
)

if "%JULES_API_KEY%"=="" (
    echo Error: JULES_API_KEY not set
    exit /b 1
)

echo Environment variables loaded
echo.

REM Check if logs directory exists
if not exist logs (
    echo Creating logs directory...
    mkdir logs
)

REM Main menu
echo Select agent to run:
echo.
echo 1) Product Manager
echo 2) Interface Developer
echo 3) Senior Developer
echo 4) PR Assistant
echo 5) All Agents (sequential)
echo 6) Exit
echo.
set /p choice="Enter choice [1-6]: "

if "%choice%"=="1" goto product_manager
if "%choice%"=="2" goto interface_developer
if "%choice%"=="3" goto senior_developer
if "%choice%"=="4" goto pr_assistant
if "%choice%"=="5" goto all_agents
if "%choice%"=="6" goto exit
goto invalid_choice

:product_manager
echo.
echo =========================================
echo Running: Product Manager
echo =========================================
echo.
uv run run-agent product-manager
goto end

:interface_developer
echo.
echo =========================================
echo Running: Interface Developer
echo =========================================
echo.
uv run run-agent interface-developer
goto end

:senior_developer
echo.
echo =========================================
echo Running: Senior Developer
echo =========================================
echo.
uv run run-agent senior-developer
goto end

:pr_assistant
echo.
echo =========================================
echo Running: PR Assistant
echo =========================================
echo.
uv run run-agent pr-assistant
goto end

:all_agents
echo.
echo =========================================
echo Running: All Agents
echo =========================================
echo.
uv run run-agent all
goto end

:invalid_choice
echo Invalid choice
exit /b 1

:exit
echo Exiting...
exit /b 0

:end
echo.
echo =========================================
echo Test Complete!
echo =========================================
echo.
echo Check logs\ directory for execution results
echo.
