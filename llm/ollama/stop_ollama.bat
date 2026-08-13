@echo off
rem "ollama app.exe" is the tray app; it watches and respawns ollama.exe
rem whenever it's killed, so it must be killed first or the server just restarts
ollama stop qwen3.5:4b
taskkill /IM "ollama app.exe" /F
taskkill /IM ollama.exe /F
if %errorlevel% == 0 (
    echo Ollama service stopped
) else (
    echo Ollama service failed to stop, or was not running
)