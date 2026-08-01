@echo off
rem pyKalfa - kurulum baslaticisi
rem Bu dosyaya cift tiklayarak calistirin.
rem
rem Windows'un 260 karakterlik dosya yolu sinirina takilmamak icin,
rem bu klasordeki dosyalar once C:\pyKalfa\pyKalfa.extension
rem klasorune kopyalanir (kaynaktaki dosyalar SILINMEZ), sonra kurulum
rem orada calistirilir. Boylece pip kurulumu her zaman kisa bir yol
rem altinda yapilmis olur.

setlocal

set "SRC=%~dp0revit\pyKalfa.extension"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"

set "DEST=C:\pyKalfa\pyKalfa.extension"

if /I "%SRC%"=="%DEST%" goto :run

if exist "%DEST%" (
    echo Eski hedef klasor bulundu, siliniyor: %DEST%
    rd /s /q "%DEST%"
    echo.
)

robocopy "%SRC%" "%DEST%" /E /XD env /NFL /NDL /NJH /NJS
if %ERRORLEVEL% GEQ 8 (
    echo.
    echo HATA: Kopyalama basarisiz oldu ^(robocopy kodu %ERRORLEVEL%^).
    pause
    exit /b 1
)

echo.
echo Kopyalama tamamlandi. Kurulum su klasorde calisacak:
echo   %DEST%
echo.
echo ONEMLI: pyRevit'e extension olarak
echo   %DEST%
echo klasorunu eklemeniz/guncellemeniz gerekiyor (bkz. KULLANIM.md Adim A.5).
echo.

set "SRC=%DEST%"

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\setup.ps1"
