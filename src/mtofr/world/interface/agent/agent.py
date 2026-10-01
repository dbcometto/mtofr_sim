"""Definition of the agentic loop. No printing here; it reports through `emit`."""
import ollama

from . import config

# Defined once and used for every request. If the warm-up and the real calls
# used different options, Ollama would reload the model and the warm-up would be wasted.
OPTIONS = {"num_ctx": config.NUM_CTX, "temperature": config.TEMPERATURE}


def warm_up(messages, tools, options=OPTIONS):
    """Load the model into RAM and process the starting prompt, before the user types.

    Asks for at most 1 token, so it returns almost immediately after loading.
    """
    ollama.chat(
        model=config.MODEL,
        messages=messages,
        tools=tools,  # same tools as real calls, so the cached prompt prefix matches
        options={**options, "num_predict": 1},  # same options, plus: generate 1 token at most
        keep_alive=config.KEEP_ALIVE,
    )


def stream_reply(messages, think, emit, tools, options=OPTIONS, should_stop=None, meta=None):
    """One model call: send the conversation, report tokens as they arrive.

    Returns (message, interrupted). The message is ready to append to the history
    and includes "tool_calls" if the model asked for any. `should_stop`, if given, is
    polled once per chunk -- the GUI's stand-in for Ctrl+C, which can't reach a worker thread.
    If `meta` (a dict) is given, meta["truncated"] is set to True when the reply hit the num_predict cap.
    """

    # Interact with model (returns generator)
    stream = ollama.chat(
        model=config.MODEL,
        messages=messages,
        tools=tools,                          # the tool descriptions the model can choose from
        stream=True,                          # yield small chunks instead of one big reply
        think=think,                          # ask the model to expose its reasoning (or not)
        options=options,                      # context window size, temperature
        keep_alive=config.KEEP_ALIVE,         # each request resets the unload timer
    )

    content = ""      # the answer text, accumulated chunk by chunk
    thinking = ""     # the reasoning text, accumulated the same way
    tool_calls = []   # tool requests; they arrive as whole objects inside chunks
    last = None       # the final chunk carries timing statistics
    interrupted = False
    chunk_count = 0

    # Iterate through tokens
    try:
        for chunk in stream:
            if should_stop is not None and should_stop():
                raise KeyboardInterrupt
            chunk_count += 1
            if chunk_count == 1:
                emit("generating", None)   # the first chunk only arrives after the prompt has been read
            last = chunk
            if chunk.message.thinking:
                thinking += chunk.message.thinking
                emit("thinking", chunk.message.thinking)
            if chunk.message.content:
                content += chunk.message.content
                emit("content", chunk.message.content)
            if chunk.message.tool_calls:
                tool_calls.extend(chunk.message.tool_calls)

    except KeyboardInterrupt:
        # Stop generating but keep what arrived so far; it still goes into history.
        interrupted = True
        emit("interrupted", None)
        if content:
            # Tell the model its reply was cut off, so it doesn't treat it as complete.
            content += " [interrupted by user]"

    if last and last.eval_count and last.eval_duration:
        rate = last.eval_count / (last.eval_duration / 1e9)  # duration is in nanoseconds
        prompt_seconds = (getattr(last, "prompt_eval_duration", None) or 0) / 1e9
        emit("stats", {"tokens": last.eval_count, "rate": rate, "seconds": last.eval_duration / 1e9,
                       "prompt_tokens": getattr(last, "prompt_eval_count", None) or 0, "prompt_seconds": prompt_seconds,
                       # eval/prompt durations exclude model (re)loading, which total_duration includes
                       "load_seconds": (getattr(last, "load_duration", None) or 0) / 1e9,
                       "total_seconds": (getattr(last, "total_duration", None) or 0) / 1e9})

    if meta is not None:
        meta["truncated"] = getattr(last, "done_reason", None) == "length"   # Ollama's marker for hitting num_predict

    # Thinking stays in history so the next loop of this same turn doesn't redo it; AssistantSession drops it when the turn ends.
    message = {"role": "assistant", "content": content}
    if thinking:
        message["thinking"] = thinking
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message, interrupted


def run_agent_turn(messages, think, emit, tools, run_tool, options=OPTIONS, should_stop=None, detect_stall=None):
    """The agentic loop: handle one user message, which may take several model calls.

    Appends everything that happens (assistant replies, tool results) to `messages`.
    `tools` are the schemas the model sees; `run_tool(name, arguments)` executes one and returns its result string.
    `emit(kind, data)` receives, besides the kinds from stream_reply:
        ("loop", dict)         a model call is starting (iteration and maximum)
        ("tool_call", dict)    the model asked for a tool (name, arguments)
        ("tool_result", dict)  what the tool returned (name, result)
        ("limit", None)        stopped because MAX_ITERATIONS was reached
        ("nudge", str)         the reply stalled without tool calls and the model was sent this retry message
        ("generating", None)   the first chunk of a model call arrived: the prompt has been read, output has begun
    `detect_stall(content, truncated)`, if given, returns a retry message when a reply with no real tool calls
    looks like a stall rather than a finished answer (calls typed as text, cut off by the length cap, or
    announcing a next step without doing it -- small-model failure modes), else None; at most MAX_NUDGES per turn.
    """
    nudges = 0
    for iteration in range(1, config.MAX_ITERATIONS + 1):
        emit("loop", {"iteration": iteration, "max": config.MAX_ITERATIONS})

        meta = {}
        reply, interrupted = stream_reply(messages, think, emit, tools, options, should_stop, meta)

        if interrupted:
            # Don't act on a request that was cut off; keep only the partial text.
            reply.pop("tool_calls", None)
            if reply["content"]:
                messages.append(reply)
            return

        if reply["content"] or reply.get("tool_calls"):
            messages.append(reply)

        # No tool calls means the model has finished its answer.
        if not reply.get("tool_calls"):
            retry_message = detect_stall(reply["content"], meta.get("truncated", False)) if detect_stall else None
            if retry_message and nudges < config.MAX_NUDGES:
                nudges += 1
                emit("nudge", retry_message)
                messages.append({"role": "user", "content": retry_message})
                continue
            return

        # Otherwise run each requested tool and feed the results back.
        for call in reply["tool_calls"]:
            name = call.function.name
            arguments = call.function.arguments
            emit("tool_call", {"name": name, "arguments": arguments})

            result = run_tool(name, arguments)
            emit("tool_result", {"name": name, "result": result})

            messages.append({"role": "tool", "tool_name": name, "content": result})
        # ...and loop: the model is called again and sees the results.

    emit("limit", None)
