"""Configuration"""

MODEL = "qwen3.5:4b"  # must match a name shown by `ollama list`
NUM_CTX = 8192        # context window in tokens; Ollama silently truncates beyond this. 14 tool schemas + a full draft don't fit in 4096
THINK = False         # show the model's reasoning? True is much slower on a CPU
TEMPERATURE = 0.5     # randomness of token choice; lower is steadier, which helps tool calls
MAX_REPLY_TOKENS = 800  # most tokens one model call may write; at ~5 tok/s CPU speed, an unbounded reply can ramble for many minutes (four tool calls need ~300)
MAX_NUDGES = 2       # most automatic "make those real tool calls" retries per user message
MAX_ITERATIONS = 12   # most model calls allowed per user message (stops runaway loops); a multi-leg mission needs many calls
KEEP_ALIVE = "30m"   # how long Ollama keeps the model in RAM after a request (default is 5m)
