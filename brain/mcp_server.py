"""The tool server over MCP.

Each MCP server process runs as one agent identity (in Azure: that agent's managed identity) and only
publishes the tools that agent may use. Every call still goes through ToolServer.call, so rights,
logging and caching are the same as for in-process calls.

  BRAIN_MCP_AGENT=agent:proposal_writer brain mcp          # stdio, for an MCP client
"""
from __future__ import annotations

import inspect
import os

from mcp.server.mcpserver import MCPServer

from . import db
from .tenant import tenant
from .identity import AGENTS, agent
from .toolserver import server as tools


def build(agent_id: str | None = None) -> MCPServer:
    agent_id = agent_id or os.getenv("BRAIN_MCP_AGENT", "agent:knowledge_desk")
    me = agent(agent_id)
    mcp = MCPServer(name=f"{tenant().tenant_id}-brain ({agent_id})",
                    instructions=f"Tools of the {tenant().name} company brain. Drafts only; nothing is sent or booked.")
    for name in sorted(AGENTS[me.id]):
        t = tools.tools.get(name)
        if t is None:
            continue
        sig = inspect.signature(t.fn)
        params = [p for p in sig.parameters.values() if p.name != "s"]

        def make(tool_name):
            def call(**kwargs):
                with db.session() as s:
                    out = tools.call(s, me, tool_name, **kwargs)
                    s.commit()
                    return out
            return call

        fn = make(name)
        fn.__signature__ = sig.replace(parameters=params)
        fn.__annotations__ = {k: v for k, v in t.fn.__annotations__.items() if k != "s"}
        fn.__name__ = name.replace(".", "_")
        mcp.add_tool(fn, name=name.replace(".", "_"), description=f"{t.description} ({t.access})")
    return mcp


def main() -> None:  # pragma: no cover
    build().run()
