@echo off
echo Cleaning build directories...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
taskkill /F /IM InstagramReposter.exe 2>nul

echo Building executable...
python -m PyInstaller --upx-dir="C:\Users\rocky\Downloads\upx-5.0.0-win64\upx-5.0.0-win64" InstagramReposter.spec

echo Build complete!
echo Executable location: %CD%\dist\InstagramReposter.exe 