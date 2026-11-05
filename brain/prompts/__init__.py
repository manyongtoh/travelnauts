"""Prompts in three layers, in this order:

1. House layer, from the tenant pack (house.md): tone, forms of address, words, what we never promise. Never
   changes per call, so providers can cache it.
2. Agent layer: the tenant pack's override for the task if it has one, else agents/<task>.md in the core, else
   the instructions in the agent's code: task, steps, output, rules.
3. Task context: the filtered mail or dossier and knowledge snippets, sent as the user message.

No timestamps or changing data in layers 1 and 2. The version (a hash of layers 1 and 2) is stored with
every model call, so a change in a prompt is traceable to its effect in the evals.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..tenant import load

HERE = Path(__file__).parent


def house_layer() -> str:
    return load().house_prompt


def agent_layer(task: str, default: str) -> str:
    override = load().agent_prompts.get(task)
    if override:
        return override
    f = HERE / "agents" / f"{task}.md"
    return f.read_text(encoding="utf-8") if f.exists() else default


def build(task: str, instructions: str) -> tuple[str, str]:
    l1, l2 = house_layer(), agent_layer(task, instructions)
    version = hashlib.sha256((l1 + "\n" + l2).encode()).hexdigest()[:10]
    return f"[task:{task}]\n{l1}\n\n# Agent layer\n{l2}", version
