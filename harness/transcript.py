"""Read an agent's full conversation back out of Claude Code's own transcript.

The harness log only holds what `claude -p --output-format json` prints: the prompt that
launched the run and its final answer. Everything in between -- every tool call, its
output, every intermediate message -- is written by Claude Code itself to

    ~/.claude/projects/<cwd with every non-alphanumeric turned into "-">/<session>.jsonl

and the session id is one this harness mints (session_lib.sh), so the registry already
holds the key. This module turns that JSONL into a flat list of readable entries.

It is a reader of someone else's file format, so it is deliberately forgiving: unknown
record types are skipped, not fatal, and nothing here writes to the transcript.
"""
from __future__ import annotations

import json
import os
import re

# Per-entry caps. A single `cat` of a parquet dump or a pytest run can be megabytes, and
# the page renders every entry at once; the full text is still on disk for anyone who
# needs it.
MAX_TEXT = 20_000
MAX_TOOL_OUTPUT = 4_000
MAX_TOOL_INPUT = 2_000


def projects_root() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects")


def project_dir(cwd: str) -> str:
    return os.path.join(projects_root(), re.sub(r"[^A-Za-z0-9]", "-", cwd))


def path_for(session_id: str, cwd: str) -> str:
    return os.path.join(project_dir(cwd), f"{session_id}.jsonl")


def _clip(s: str, n: int) -> tuple[str, bool]:
    if len(s) <= n:
        return s, False
    return s[:n] + f"\n… [{len(s) - n:,} more characters not shown]", True


def _tool_input(name: str, inp: dict) -> str:
    """The part of a tool call a reader wants, not its full JSON."""
    if not isinstance(inp, dict):
        return str(inp)
    if name == "Bash":
        cmd = inp.get("command", "")
        desc = inp.get("description")
        return f"# {desc}\n{cmd}" if desc else cmd
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        head = inp.get("file_path") or inp.get("notebook_path") or ""
        if name == "Edit":
            return (f"{head}\n--- old\n{inp.get('old_string', '')}"
                    f"\n+++ new\n{inp.get('new_string', '')}")
        if name == "Write":
            return f"{head}\n{inp.get('content', '')}"
        return head
    if name in ("Grep", "Glob"):
        return " ".join(f"{k}={v}" for k, v in inp.items())
    return json.dumps(inp, ensure_ascii=False, indent=1)


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif c.get("type") == "image":
                parts.append("[image]")
        return "\n".join(parts)
    return "" if content is None else str(content)


def render(path: str) -> dict:
    """{"entries": [...], "model": str|None, "bytes": int} for one transcript file.

    Each entry is {"ts", "kind", "text"} plus "tool" / "error" / "clipped" where they
    apply. kind is one of: user, assistant, thinking, tool_use, tool_result.
    """
    entries, model, names = [], None, {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue                      # a half-written last line of a live run
            typ = rec.get("type")
            if typ not in ("user", "assistant"):
                continue
            msg = rec.get("message") or {}
            ts = rec.get("timestamp")
            if typ == "assistant" and msg.get("model") and msg["model"] != "<synthetic>":
                model = msg["model"]
            content = msg.get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for c in content or []:
                if not isinstance(c, dict):
                    continue
                ct = c.get("type")
                e = None
                if ct == "text" and c.get("text", "").strip():
                    text, clipped = _clip(c["text"], MAX_TEXT)
                    e = {"kind": typ, "text": text, "clipped": clipped}
                elif ct == "thinking" and c.get("thinking", "").strip():
                    text, clipped = _clip(c["thinking"], MAX_TEXT)
                    e = {"kind": "thinking", "text": text, "clipped": clipped}
                elif ct == "tool_use":
                    names[c.get("id")] = c.get("name", "?")
                    text, clipped = _clip(_tool_input(c.get("name", ""), c.get("input")),
                                          MAX_TOOL_INPUT)
                    e = {"kind": "tool_use", "tool": c.get("name", "?"), "text": text,
                         "clipped": clipped}
                elif ct == "tool_result":
                    text, clipped = _clip(_result_text(c.get("content")), MAX_TOOL_OUTPUT)
                    e = {"kind": "tool_result", "tool": names.get(c.get("tool_use_id"), "?"),
                         "text": text, "clipped": clipped, "error": bool(c.get("is_error"))}
                if e:
                    e["ts"] = ts
                    entries.append(e)
    return {"entries": entries, "model": model, "bytes": os.path.getsize(path)}
