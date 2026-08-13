@echo off
rem errorlevel here only reflects whether cmd could launch ollama.exe at all,
rem not whether the server bound its port successfully (start returns immediately)
start /min ollama serve
if %errorlevel% == 0 (
    echo Ollama service started
) else (
    echo Ollama service failed to start
)