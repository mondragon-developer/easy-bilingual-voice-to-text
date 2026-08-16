@echo off
REM ---------------------------------------------------------------------------
REM Shipped inside the Windows CPU zip as "Modo espanol.bat".
REM
REM The default model, `small`, writes every Spanish word correctly but drops
REM the accents on proper nouns and the opening "inverted" question mark. The
REM `medium` model gets both right. It is about three times slower, which is
REM why it is not the default: on English the two produce byte-identical text,
REM so most people would pay the time for nothing.
REM
REM This exists so a Spanish speaker does not need to know what an environment
REM variable is. Double-click, and the app starts with the better model.
REM
REM Not shipped in the GPU zip: that build already uses `large-v3`, which
REM handles Spanish correctly and would be downgraded by this.
REM ---------------------------------------------------------------------------

set STT_MODEL=medium

echo.
echo   Speech to Text - modo espanol / Spanish mode
echo.
echo   Starting with the "medium" model, for correct accents and
echo   question marks in Spanish.
echo.
echo   The first time only, this downloads about 1.4 GB. After that
echo   it starts as quickly as usual.
echo.

start "" "%~dp0SpeechToText.exe"
