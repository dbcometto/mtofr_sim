# Local LLM setup (Ollama)

The mission-commander LLM runs locally via [Ollama](https://ollama.com), CPU-only, on the model `qwen3.5:4b`. No cloud API is used: the Claude API has no sustained free tier for this use case, and Ollama Cloud is a separate paid product, not what's used here.

Everything for this lives under `llm/ollama/`: the start/stop scripts and `llm_config.yaml`.

## Setup

### 1. Install Ollama

Windows: download and run the installer from https://ollama.com, then verify with:

```bash
ollama -v
```

### 2. Disable auto-start

The installer registers a tray app (`ollama app.exe`) to start automatically at login; disable this via Task Manager (Startup tab) so the service only runs when explicitly started via the scripts below. Note this only stops the tray app launching at the *next* login -- it does not quit an already-running instance. The tray app also acts as a watchdog that respawns `ollama.exe` (the actual server) whenever it's killed, so if `ollama app.exe` is already running, killing just `ollama.exe` (e.g. via Task Manager) won't actually stop the service -- it'll be back within moments. `stop_ollama.bat` (below) kills both, in the right order, for exactly this reason.

### 3. Pull the model

```bash
ollama pull qwen3.5:4b
```

Downloads ~3.4GB to `C:\Users\<username>\.ollama\models` by default. Model weights live outside the repo -- only the model name (`qwen3.5:4b`) is referenced in config.

### 4. Start / stop the service

```bash
llm\ollama\start_ollama.bat
llm\ollama\stop_ollama.bat
```

Both scripts echo a success/failure message based on `%errorlevel%`. Note this only reflects whether `cmd` could launch/signal `ollama.exe` at all -- `start /min` returns as soon as the process is launched, not once the server has actually finished binding its port, so a runtime failure (e.g. port already in use) won't be caught by this check. The echoed output is plain stdout text, so calling these scripts from a Python script (e.g. via `subprocess.run(...)`) is unaffected by it -- there's no interactive prompt to get stuck on.

## Usage

### CLI vs API

Two distinct ways to talk to the running service:

- **CLI** (`ollama run qwen3.5:4b`): interactive chat in the terminal, for manual testing. Ollama manages conversation history for you automatically.
- **API** (`POST http://localhost:11434/api/chat`): what mtofr code will call. This endpoint is stateless -- each request must include the full conversation history; nothing is remembered server-side between calls. This is the integration point for the (not yet built) Python client.

### Config

`llm/ollama/llm_config.yaml` holds the model name, system prompt, and generation params (`temperature`, `num_predict`, `keep_alive`) as plain data, intended to be loaded by Python code and passed explicitly on each `/api/chat` call -- nothing is baked into the model itself via `ollama create`, so changing any of it doesn't require rebuilding a model. Not yet loaded by any Python code.

## Current status

- Ollama installed, model pulled, scripts working manually.
- No Python `/api/chat` client yet, no streaming, no agentic tool-call loop, no eval set against the mission-graph tool schema. All future work.