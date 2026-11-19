# Mission-Type Orders for Robotics, Simulator

A simulator for implementing domain- and platform-agnostic mission-type orders for robots.


## Installation

### Requirements

To get started, clone the repo, make a virtual environment at the repo root, activate it, and run
```bash
pip install -e ./mtofr
```
from the repo root.


### Ollama

The mission-commander LLM runs locally via Ollama, CPU-only. See [`docs/llm_setup.md`](docs/llm_setup.md) for the full install/setup workflow and CLI-vs-API usage notes.


## Usage

Run the simulator (pick the mission set with `ACTIVE_MISSION_SET` at the top of `main.py`):
```bash
python main.py
```

Run the tests:
```bash
python -m unittest discover -s tests
```


## Documentation

- [`docs/spec.md`](docs/spec.md): architecture overview
- [`docs/roadmap.md`](docs/roadmap.md): build order, open items, known issues
- [`docs/notes.md`](docs/notes.md): design history
- [`docs/proc.md`](docs/proc.md), [`docs/style.md`](docs/style.md): development process and code style