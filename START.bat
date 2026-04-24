@echo off
setlocal enabledelayedexpansion
title LinkedIn Lead Generator
color 0B

cd /d "%~dp0"
echo ====================================================
echo      LinkedIn Lead Generator
echo      Influencer Marketing Outreach Tool
echo ====================================================
echo.

echo Select operation mode:
echo   [1] FULL     - Search, Connect, ^& DM (all-in-one)
echo   [2] SEARCH   - Search ^& scrape only (no outreach)
echo   [3] CONNECT  - Send connection requests only
echo   [4] FOLLOWUP - DM accepted connections
echo.
set /p MODE_CHOICE="Enter choice (1-4): "

set "SCRAPE_MODE=search"
if "%MODE_CHOICE%"=="1" set "SCRAPE_MODE=full"
if "%MODE_CHOICE%"=="2" set "SCRAPE_MODE=search"
if "%MODE_CHOICE%"=="3" set "SCRAPE_MODE=connect"
if "%MODE_CHOICE%"=="4" set "SCRAPE_MODE=followup"

echo.
echo Available industries:
echo   1. Technology ^& SaaS
echo   2. Fashion ^& Apparel
echo   3. Beauty ^& Skincare
echo   4. Fitness ^& Health
echo   5. E-commerce ^& D2C
echo   6. Food ^& Beverage
echo   7. Real Estate
echo   8. Education ^& EdTech
echo   9. Travel ^& Hospitality
echo   0. ALL (search all industries)
echo.
set /p IND_CHOICE="Enter industry numbers separated by spaces (e.g., 1 2 5) or 0 for ALL: "

set "INDUSTRIES="
set "USE_INDUSTRIES=0"

if "%IND_CHOICE%"=="0" goto :skip_industries

set "USE_INDUSTRIES=1"
for %%i in (%IND_CHOICE%) do (
    if "%%i"=="1" set "INDUSTRIES=!INDUSTRIES! Technology_SaaS"
    if "%%i"=="2" set "INDUSTRIES=!INDUSTRIES! Fashion_Apparel"
    if "%%i"=="3" set "INDUSTRIES=!INDUSTRIES! Beauty_Skincare"
    if "%%i"=="4" set "INDUSTRIES=!INDUSTRIES! Fitness_Health"
    if "%%i"=="5" set "INDUSTRIES=!INDUSTRIES! Ecommerce_D2C"
    if "%%i"=="6" set "INDUSTRIES=!INDUSTRIES! Food_Beverage"
    if "%%i"=="7" set "INDUSTRIES=!INDUSTRIES! RealEstate"
    if "%%i"=="8" set "INDUSTRIES=!INDUSTRIES! Education_EdTech"
    if "%%i"=="9" set "INDUSTRIES=!INDUSTRIES! Travel_Hospitality"
)
:skip_industries

set /p MAX_COMPANIES="Max companies per industry? (Just press Enter for 20): "
if "%MAX_COMPANIES%"=="" set "MAX_COMPANIES=20"

echo.
echo ----------------------------------------------------
echo Mode        : %SCRAPE_MODE%
if "%USE_INDUSTRIES%"=="1" (
    echo Industries  : !INDUSTRIES!
) else (
    echo Industries  : ALL
)
echo Max Companies: %MAX_COMPANIES% per industry
echo Please do not close this window until it finishes.
echo ----------------------------------------------------
echo.

if "%USE_INDUSTRIES%"=="0" (
    python main.py --mode %SCRAPE_MODE% --max-companies %MAX_COMPANIES%
) else (
    python main.py --mode %SCRAPE_MODE% --industries !INDUSTRIES! --max-companies %MAX_COMPANIES%
)

echo.
echo ----------------------------------------------------
echo  Done! Check the data folder for results.
echo ----------------------------------------------------
endlocal
pause
