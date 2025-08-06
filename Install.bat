@echo off
setlocal

echo === Setting up Python and Node.js ===

:: Define URLs for latest installers
set PYTHON_URL=https://www.python.org/ftp/python/3.11.6/python-3.11.6-amd64.exe
set NODE_URL=https://nodejs.org/dist/v20.5.1/node-v20.5.1-x64.msi

:: Define installer filenames
set PYTHON_INSTALLER=python_installer.exe
set NODE_INSTALLER=node_installer.msi

:: Download Python
echo Downloading Python...
powershell -Command "Invoke-WebRequest -Uri %PYTHON_URL% -OutFile %PYTHON_INSTALLER%"

:: Install Python silently
echo Installing Python...
start /wait %PYTHON_INSTALLER% /quiet InstallAllUsers=1 PrependPath=1 Include_test=0

:: Download Node.js
echo Downloading Node.js...
powershell -Command "Invoke-WebRequest -Uri %NODE_URL% -OutFile %NODE_INSTALLER%"

:: Install Node.js silently
echo Installing Node.js...
start /wait msiexec /i %NODE_INSTALLER% /quiet

:: Cleanup
del %PYTHON_INSTALLER%
del %NODE_INSTALLER%

echo === Installation Complete ===
python --version
node --version
npm --version

endlocal
pause