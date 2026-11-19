# CLAUDE Instructions

MTOFR_SIM: a simulator for platform-agnostic mission-type orders for robots (pure Python).


## Current status
The peer-to-peer platform stack, image-based maps, default missions, the mission editor (interface platform), and a first cut of its LLM assistant are complete (build order steps 1-6 and part of 7).  The next step is a post-turn graph check fed back to the assistant, then logistics (step 8).  Run with `.venv\Scripts\python.exe main.py`; test with `.venv\Scripts\python.exe -m unittest discover -s tests`.


## What to do
@docs/proc.md

## How to do it
@docs/style.md

## Overall picture
@docs/spec.md

## Roadmap
@docs/roadmap.md

## Detailed log
Can be found under `./docs/notes.md`, only load it if needed.  Local LLM (Ollama) setup is in `./docs/llm_setup.md`.
