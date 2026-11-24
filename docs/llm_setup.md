# Local LLM setup (Ollama)

The mission-commander LLM runs locally via [Ollama](https://ollama.com), CPU-only, on the model `qwen3.5:4b`. No cloud API is used: the Claude API has no sustained free tier for this use case, and Ollama Cloud is a separate paid product, not what's used here.

The start/stop scripts live under `llm/ollama/`.  The model settings (model name, context size, temperature, reply cap, keep-alive, ...) live in `src/mtofr/environments/ground_plane/platforms/interface/agent/config.py`, and are passed on each call rather than baked into a model with `ollama create`, so changing them needs no rebuild.

## Setup

### 1. Install Ollama

Windows: download and run the installer from https://ollama.com, then verify with:

```bash
ollama -v
```

The Python client (`ollama` package) is a project dependency.

### 2. Disable auto-start

The installer registers a tray app (`ollama app.exe`) to start automatically at login; disable this via Task Manager (Startup tab) so the service only runs when explicitly started via the scripts below. Note this only stops the tray app launching at the *next* login -- it does not quit an already-running instance. The tray app also acts as a watchdog that respawns `ollama.exe` (the actual server) whenever it's killed, so if `ollama app.exe` is already running, killing just `ollama.exe` (e.g. via Task Manager) won't actually stop the service -- it'll be back within moments. `stop_ollama.bat` (below) kills both, in the right order, for exactly this reason.

### 3. Pull the model

```bash
ollama pull qwen3.5:4b
```

Downloads ~3.4GB to `C:\Users\<username>\.ollama\models` by default. Model weights live outside the repo -- only the model name is referenced in config.

### 4. Start / stop the service

```bash
llm\ollama\start_ollama.bat
llm\ollama\stop_ollama.bat
```

Both scripts echo a success/failure message based on `%errorlevel%`. Note this only reflects whether `cmd` could launch/signal `ollama.exe` at all -- `start /min` returns as soon as the process is launched, not once the server has actually finished binding its port, so a runtime failure (e.g. port already in use) won't be caught by this check.

## Usage

- **In the simulator**: start the service, run `main.py` with a scenario that includes the interface platform (e.g. `VILLAGE_DEFAULT`), and click "Assistant..." in the mission editor.  See `spec.md`'s LLM Assistant section for how it works.
- **CLI** (`ollama run qwen3.5:4b`): interactive chat in the terminal, for manual testing. Ollama manages conversation history for you.
- **API**: the simulator uses the `ollama` Python client (`/api/chat`), which is stateless -- each request carries the full conversation history.

## Current status

Working end to end against the real model at ~4-5 tok/s on CPU; see `roadmap.md` for open items.  The real-model runs are slow, so the user runs them.
