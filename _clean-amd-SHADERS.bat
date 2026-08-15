@echo off
setlocal EnableDelayedExpansion
title GPU Shader Cache Cleanup Utility

:: =====================================================================
:: GPU Shader Cache Cleanup Utility
::
:: Usage:
::   clean-gpu-shaders.bat            -> interactive menu, pick what to clear
::   clean-gpu-shaders.bat /ALL       -> clear EVERYTHING, incl. Steam, no prompts
::   clean-gpu-shaders.bat /DEFAULT   -> clear everything except Steam, no prompts
::   clean-gpu-shaders.bat /WINDOWS   -> clear Windows/DirectX caches only
::   clean-gpu-shaders.bat /AMD       -> clear AMD caches only
::   clean-gpu-shaders.bat /NVIDIA    -> clear NVIDIA caches only
::   clean-gpu-shaders.bat /INTEL     -> clear Intel caches only
::   clean-gpu-shaders.bat /STEAM     -> clear Steam shader cache only
::   clean-gpu-shaders.bat /PRESET:x  -> same as above, e.g. /PRESET:AMD
::   clean-gpu-shaders.bat /LIST      -> just list detected caches and sizes
::   clean-gpu-shaders.bat /HELP      -> show this usage text
::   clean-gpu-shaders.bat /LOG:path  -> write log to a custom path
::
:: In the interactive menu, leaving your answer blank runs the DEFAULT
:: preset (everything except Steam).
:: =====================================================================

set "SCRIPT_DIR=%~dp0"
set "LOGFILE=%SCRIPT_DIR%ShaderCacheCleanup.log"
set "MODE=MENU"
set "PRESET_NAME="
set "TOTAL_FREED=0"

:: ---- Parse arguments --------------------------------------------------
:ParseArgs
if "%~1"=="" goto ArgsDone
set "ARG=%~1"
if /I "%ARG%"=="/ALL"      set "MODE=PRESET" & set "PRESET_NAME=ALL"     & shift & goto ParseArgs
if /I "%ARG%"=="/DEFAULT"  set "MODE=PRESET" & set "PRESET_NAME=DEFAULT" & shift & goto ParseArgs
if /I "%ARG%"=="/WINDOWS"  set "MODE=PRESET" & set "PRESET_NAME=WIN"     & shift & goto ParseArgs
if /I "%ARG%"=="/AMD"      set "MODE=PRESET" & set "PRESET_NAME=AMD"     & shift & goto ParseArgs
if /I "%ARG%"=="/NVIDIA"   set "MODE=PRESET" & set "PRESET_NAME=NVIDIA"  & shift & goto ParseArgs
if /I "%ARG%"=="/INTEL"    set "MODE=PRESET" & set "PRESET_NAME=INTEL"   & shift & goto ParseArgs
if /I "%ARG%"=="/STEAM"    set "MODE=PRESET" & set "PRESET_NAME=STEAM"   & shift & goto ParseArgs
if /I "%ARG%"=="/LIST"     set "MODE=LIST" & shift & goto ParseArgs
if /I "%ARG%"=="/HELP"     goto ShowHelp
if /I "%ARG:~0,8%"=="/PRESET:" (
    set "MODE=PRESET"
    set "PRESET_NAME=%ARG:~8%"
    shift
    goto ParseArgs
)
if /I "%ARG:~0,5%"=="/LOG:" (
    set "LOGFILE=%ARG:~5%"
    shift
    goto ParseArgs
)
echo Unrecognized argument: %ARG%
echo.
goto ShowHelp

:ArgsDone

:: ---- Admin check --------------------------------------------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo =====================================================
    echo  WARNING: Not running as Administrator.
    echo  Some caches may be locked and cannot be fully cleared.
    echo  Right-click this script and choose "Run as administrator"
    echo  for best results, ideally in Safe Mode.
    echo =====================================================
    echo.
    if /I "%MODE%"=="MENU" (
        choice /C YN /M "Continue anyway"
        if errorlevel 2 exit /b 1
    )
    echo.
)

:: ---- Check for handle.exe (optional, used to report lockers) -----------
set "HAVE_HANDLE=0"
where handle.exe >nul 2>&1
if %errorlevel%==0 set "HAVE_HANDLE=1"

:: ---- Define the cache list ----------------------------------------------
:: Add new entries by bumping CACHE_COUNT and adding a matching pair below.
:: 3rd argument is the vendor tag used by the bundle presets below:
::   WIN | AMD | NVIDIA | INTEL | STEAM
set /a CACHE_COUNT=0

call :AddCache "%LOCALAPPDATA%\D3DSCache"                              "Windows DirectX Shader Cache"          WIN
call :AddCache "%LOCALAPPDATA%\Temp\DXCache"                           "DX12 Pipeline Cache"                   WIN
call :AddCache "%LOCALAPPDATA%\Microsoft\DirectX Shader Cache"         "Windows DirectX Alt Cache"              WIN
call :AddCache "%LOCALAPPDATA%\Temp\D3DCache"                          "Direct3D Pipeline Cache"                WIN

call :AddCache "%LOCALAPPDATA%\AMD\DXCache"                            "AMD DX Cache"                           AMD
call :AddCache "%LOCALAPPDATA%\AMD\GLCache"                            "AMD OpenGL Cache"                       AMD
call :AddCache "%LOCALAPPDATA%\AMD\VkCache"                            "AMD Vulkan Cache"                       AMD

call :AddCache "%LOCALAPPDATA%\Temp\NVIDIA Corporation\NV_Cache"       "NVIDIA Pipeline Cache"                  NVIDIA
call :AddCache "%LOCALAPPDATA%\NVIDIA\DXCache"                         "NVIDIA DX Cache"                        NVIDIA
call :AddCache "%LOCALAPPDATA%\NVIDIA\GLCache"                         "NVIDIA OpenGL Cache"                    NVIDIA
call :AddCache "%LOCALAPPDATA%\NVIDIA\VkCache"                         "NVIDIA Vulkan Cache"                    NVIDIA
call :AddCache "%APPDATA%\NVIDIA\ComputeCache"                         "NVIDIA Compute Cache"                   NVIDIA
call :AddCache "%LOCALAPPDATA%\NVIDIA App\DXCache"                     "NVIDIA App DX Cache"                    NVIDIA
call :AddCache "%LOCALAPPDATA%\NVIDIA App\GLCache"                     "NVIDIA App OpenGL Cache"                NVIDIA
call :AddCache "%LOCALAPPDATA%\NVIDIA App\VkCache"                     "NVIDIA App Vulkan Cache"                NVIDIA

call :AddCache "%LOCALAPPDATA%\Intel\ShaderCache"                      "Intel Shader Cache"                     INTEL

call :AddCache "%PROGRAMFILES(X86)%\Steam\steamapps\shadercache"       "Steam Shader Cache (default library)"   STEAM

:: ---- Dispatch by mode -----------------------------------------------------
if /I "%MODE%"=="LIST"   goto DoList
if /I "%MODE%"=="PRESET" goto DoPreset
goto DoMenu

:: =========================================================================
:DoList
echo.
echo ==========================================
echo  Detected caches
echo ==========================================
for /L %%i in (1,1,%CACHE_COUNT%) do (
    call :ReportOne %%i
)
echo.
pause
exit /b

:: =========================================================================
:: Clears a named bundle. PRESET_NAME must already be set.
::   ALL      = every cache, including Steam
::   DEFAULT  = every cache EXCEPT Steam
::   WIN / AMD / NVIDIA / INTEL / STEAM = just that vendor's caches
:DoPreset
if "%PRESET_NAME%"=="" set "PRESET_NAME=DEFAULT"
call :InitLog
echo.
echo ==========================================
echo  Clearing preset: %PRESET_NAME%
echo ==========================================
echo.
call :ClearByVendor %PRESET_NAME%
goto Summary

:: =========================================================================
:DoMenu
echo =====================================================
echo           GPU Shader Cache Cleanup Utility
echo =====================================================
echo.
echo Recommended usage:
echo  1. Run this in Normal or SAFE MODE before installing/updating
echo     GPU drivers. Safe Mode lets more caches be removed since
echo     drivers aren't actively locking files.
echo  2. If you're seeing stutter, frame pacing issues, glitches, or
echo     instability, clearing caches after a driver update can help.
echo.
echo Individual caches:
echo.
for /L %%i in (1,1,%CACHE_COUNT%) do (
    call :ShowMenuLine %%i
)
echo.
echo Presets - clear a whole device bundle at once:
echo   WIN     = Windows / DirectX caches only
echo   AMD     = AMD caches only
echo   NVIDIA  = NVIDIA caches only
echo   INTEL   = Intel caches only
echo   STEAM   = Steam shader cache only
echo   A       = Everything above, including Steam
echo   Q       = Quit without changes
echo.
echo Enter cache numbers (e.g. 1,3,5), a preset name above, or just press
set /p "SELECTION=Enter for the default preset (everything except Steam): "

if "%SELECTION%"=="" (
    set "PRESET_NAME=DEFAULT"
    goto DoPreset
)
if /I "%SELECTION%"=="Q" exit /b 0
if /I "%SELECTION%"=="A" (
    set "PRESET_NAME=ALL"
    goto DoPreset
)
if /I "%SELECTION%"=="WIN" (
    set "PRESET_NAME=WIN"
    goto DoPreset
)
if /I "%SELECTION%"=="AMD" (
    set "PRESET_NAME=AMD"
    goto DoPreset
)
if /I "%SELECTION%"=="NVIDIA" (
    set "PRESET_NAME=NVIDIA"
    goto DoPreset
)
if /I "%SELECTION%"=="INTEL" (
    set "PRESET_NAME=INTEL"
    goto DoPreset
)
if /I "%SELECTION%"=="STEAM" (
    set "PRESET_NAME=STEAM"
    goto DoPreset
)

call :InitLog
echo.
:: normalize commas to spaces, then clear each chosen index
set "SELECTION=%SELECTION:,= %"
for %%n in (%SELECTION%) do (
    set "VALID=0"
    for /L %%i in (1,1,%CACHE_COUNT%) do if "%%n"=="%%i" set "VALID=1"
    if "!VALID!"=="1" (
        call :ClearCache %%n
    ) else (
        echo Skipping invalid selection: %%n
    )
)
goto Summary

:: =========================================================================
:: Helpers below
:: =========================================================================

:AddCache
set /a CACHE_COUNT+=1
set "CACHE_PATH_%CACHE_COUNT%=%~1"
set "CACHE_NAME_%CACHE_COUNT%=%~2"
set "CACHE_VENDOR_%CACHE_COUNT%=%~3"
exit /b

:InitLog
echo ========================================== > "%LOGFILE%"
echo Shader Cache Cleanup Log >> "%LOGFILE%"
echo %date% %time% >> "%LOGFILE%"
echo ========================================== >> "%LOGFILE%"
exit /b

:: %1 = vendor keyword: ALL, DEFAULT (=ALL except STEAM), or a vendor tag
:ClearByVendor
set "want=%~1"
if /I "%want%"=="ALL" (
    for /L %%i in (1,1,%CACHE_COUNT%) do call :ClearCache %%i
    exit /b
)
if /I "%want%"=="DEFAULT" (
    for /L %%i in (1,1,%CACHE_COUNT%) do (
        set "v=!CACHE_VENDOR_%%i!"
        if /I not "!v!"=="STEAM" call :ClearCache %%i
    )
    exit /b
)
set "MATCHED=0"
for /L %%i in (1,1,%CACHE_COUNT%) do (
    set "v=!CACHE_VENDOR_%%i!"
    if /I "!v!"=="%want%" (
        set "MATCHED=1"
        call :ClearCache %%i
    )
)
if "%MATCHED%"=="0" (
    echo [WARN] Unknown preset "%want%" - nothing matched.
    echo [WARN] Unknown preset "%want%" - nothing matched. >> "%LOGFILE%"
)
exit /b

:: %1 = index, prints a numbered menu line with found/not-found status
:ShowMenuLine
set "idx=%~1"
set "p=!CACHE_PATH_%idx%!"
set "n=!CACHE_NAME_%idx%!"
set "v=!CACHE_VENDOR_%idx%!"
if exist "!p!" (
    echo   [%idx%] !n!  ^(!v!^)
) else (
    echo   [%idx%] !n!  ^(!v!^)  - not found, will be skipped
)
exit /b

:: %1 = index, used by /LIST to show name + size without deleting
:ReportOne
set "idx=%~1"
set "p=!CACHE_PATH_%idx%!"
set "n=!CACHE_NAME_%idx%!"
set "v=!CACHE_VENDOR_%idx%!"
if not exist "!p!" (
    echo   [--] !n!  ^(!v!^) - not present
    exit /b
)
call :GetFolderSize "!p!" SZ
call :HumanSize !SZ! SZDISPLAY
echo   [OK] !n!  ^(!v!^) - !SZDISPLAY!  ^(!p!^)
exit /b

:: %1 = index to clear
:ClearCache
set "idx=%~1"
set "folder=!CACHE_PATH_%idx%!"
set "name=!CACHE_NAME_%idx%!"

if not exist "%folder%" (
    echo [SKIP] %name% not found
    echo [SKIP] %name% not found >> "%LOGFILE%"
    exit /b
)

call :GetFolderSize "%folder%" PRESIZE

echo Clearing %name%...
echo Clearing %name% ^(%folder%^)... >> "%LOGFILE%"

rd /s /q "%folder%" >nul 2>&1

if exist "%folder%" (
    echo [LOCKED] %name%
    echo [LOCKED] %name% >> "%LOGFILE%"

    if "%HAVE_HANDLE%"=="1" (
        echo --- LOCKING PROCESSES --- >> "%LOGFILE%"
        handle.exe -accepteula "%folder%" >> "%LOGFILE%" 2>&1
        echo --- END LOCKING PROCESSES --- >> "%LOGFILE%"
    ) else (
        echo [INFO] handle.exe not found in PATH - skipping locker report >> "%LOGFILE%"
    )

    echo [INFO] Could not fully clear %name% - close the app/driver using it and re-run
    echo [INFO] Could not fully clear %name% >> "%LOGFILE%"
) else (
    call :HumanSize !PRESIZE! FREEDDISPLAY
    echo [OK] %name% - freed !FREEDDISPLAY!
    echo [OK] %name% - freed !FREEDDISPLAY! >> "%LOGFILE%"
    set /a TOTAL_FREED+=PRESIZE
)

if not exist "%folder%" md "%folder%" >nul 2>&1
exit /b

:: %1 = folder path, %2 = name of var to receive size in KB (rounded up)
:: NOTE: batch's "set /a" only does 32-bit signed math, so we track
:: everything in KB (not bytes) to avoid overflow once totals cross ~2GB.
:GetFolderSize
set "_gfs_path=%~1"
set "_gfs_result=0"
for /f "usebackq delims=" %%s in (`powershell -NoProfile -Command "[math]::Ceiling((Get-ChildItem -LiteralPath '%_gfs_path%' -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1KB)"`) do set "_gfs_result=%%s"
if "%_gfs_result%"=="" set "_gfs_result=0"
set "%~2=%_gfs_result%"
exit /b

:: %1 = size in KB, %2 = name of var to receive human readable string
:HumanSize
set /a _hs_kb=%~1
if %_hs_kb% GEQ 1048576 (
    set /a _hs_val=_hs_kb/1048576
    set "%~2=~!_hs_val! GB"
) else if %_hs_kb% GEQ 1024 (
    set /a _hs_val=_hs_kb/1024
    set "%~2=~!_hs_val! MB"
) else (
    set "%~2=!_hs_kb! KB"
)
exit /b

:Summary
call :HumanSize !TOTAL_FREED! TOTALDISPLAY
echo.
echo ==========================================
echo Cleanup complete
echo Total space freed: !TOTALDISPLAY!
echo Log saved to:
echo %LOGFILE%
echo ==========================================
echo.
echo Cleanup complete - freed !TOTALDISPLAY! >> "%LOGFILE%"
echo. >> "%LOGFILE%"
pause
exit /b

:ShowHelp
echo GPU Shader Cache Cleanup Utility
echo.
echo Usage:
echo   %~nx0            Interactive menu - choose caches or a preset
echo   %~nx0 /ALL       Clear EVERYTHING, including Steam
echo   %~nx0 /DEFAULT   Clear everything except Steam
echo   %~nx0 /WINDOWS   Clear Windows / DirectX caches only
echo   %~nx0 /AMD       Clear AMD caches only
echo   %~nx0 /NVIDIA    Clear NVIDIA caches only
echo   %~nx0 /INTEL     Clear Intel caches only
echo   %~nx0 /STEAM     Clear Steam shader cache only
echo   %~nx0 /PRESET:x  Same as the flags above, e.g. /PRESET:AMD
echo   %~nx0 /LIST      List detected caches and their sizes, clear nothing
echo   %~nx0 /LOG:path  Write the log file to a custom path
echo   %~nx0 /HELP      Show this help text
echo.
echo In the interactive menu, pressing Enter with no input runs the
echo DEFAULT preset (everything except Steam).
echo.
pause
exit /b