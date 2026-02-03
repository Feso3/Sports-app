@echo off
echo ============================================================
echo Collecting 5 seasons of NHL data (game logs + shots)
echo ============================================================
echo.

echo [1/6] Season 2019-2020
python -m src.collectors.run collect --game-logs --season 20192020
python -m src.collectors.run shots --season 20192020

echo [2/6] Season 2020-2021
python -m src.collectors.run collect --game-logs --season 20202021
python -m src.collectors.run shots --season 20202021

echo [3/6] Season 2021-2022
python -m src.collectors.run collect --game-logs --season 20212022
python -m src.collectors.run shots --season 20212022

echo [4/6] Season 2022-2023
python -m src.collectors.run collect --game-logs --season 20222023
python -m src.collectors.run shots --season 20222023

echo [5/6] Season 2023-2024
python -m src.collectors.run collect --game-logs --season 20232024
python -m src.collectors.run shots --season 20232024

echo [6/6] Season 2024-2025
python -m src.collectors.run collect --game-logs --season 20242025
python -m src.collectors.run shots --season 20242025

echo.
echo ============================================================
echo Collection complete!
echo ============================================================
pause
