"""Command line: brain seed | serve | bench | triage | ask "question"."""
from __future__ import annotations

import argparse
import json


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="brain", description="Travelnauts company brain sandbox (synthetic data only)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sd = sub.add_parser("seed", help="(re)build the synthetic database")
    sd.add_argument("--seed", type=int, default=None)
    sv = sub.add_parser("serve", help="run the API and the screens")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--host", default="127.0.0.1")
    bn = sub.add_parser("bench", help="run the test bench (rebuilds the database)")
    bn.add_argument("--seed", type=int, default=None)
    bn.add_argument("--gate", action="store_true", help="exit with an error when a gate fails (for CI)")
    sub.add_parser("triage", help="triage all new mail")
    ig = sub.add_parser("ingest", help="load a TravelSpirit export through the anonymiser (anonymised stage)")
    ig.add_argument("path")
    wk = sub.add_parser("worker", help="run the scheduler and job worker")
    wk.add_argument("--once", action="store_true")
    sub.add_parser("mcp", help="serve the tool server over MCP (stdio) as BRAIN_MCP_AGENT")
    sub.add_parser("reindex", help="re-read the knowledge vault")
    n8 = sub.add_parser("n8n", help="inventory of exported n8n workflows")
    n8.add_argument("paths", nargs="+")
    sub.add_parser("envcheck", help="check this environment's configuration (test, pilot, live)")
    ak = sub.add_parser("ask", help="ask the brain a question")
    ak.add_argument("question")
    a = p.parse_args(argv)

    from .config import get_settings
    get_settings()
    if a.cmd == "seed":
        from .synth.generate import build
        print(json.dumps(build(a.seed if a.seed is not None else get_settings().seed), indent=2))
    elif a.cmd == "serve":
        import uvicorn
        uvicorn.run("brain.api.app:app", host=a.host, port=a.port)
    elif a.cmd == "bench":
        import sys
        from .evals.bench import run, to_markdown
        rep = run(a.seed)
        print(to_markdown(rep))
        if a.gate and not rep["gates"]["passed"]:
            print("GATES FAILED:", [k for k, g in rep["gates"]["checks"].items() if not g["ok"]])
            sys.exit(1)
    elif a.cmd == "triage":
        from . import db
        from .agents.triage import triage_inbox
        with db.session() as s:
            for r in triage_inbox(s):
                print(r["category"], r.get("destination"), r.get("team_id"), r["summary"])
    elif a.cmd == "ingest":
        from . import db
        from .ingest import ingest
        db.create_all()
        print(json.dumps(ingest(a.path), indent=2))
    elif a.cmd == "worker":
        from . import db
        from .jobs import loop, schedule_tick, work
        db.create_all()
        if a.once:
            with db.session() as s:
                print(json.dumps({"scheduled": schedule_tick(s), "worked": work(s)}, indent=2, default=str))
        else:
            loop()
    elif a.cmd == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
    elif a.cmd == "reindex":
        from . import db
        from .knowledge.vault import reindex
        with db.session() as s:
            print(json.dumps(reindex(s), indent=2))
    elif a.cmd == "n8n":
        from .n8n_inventory import main as n8n_main
        n8n_main(a.paths)
    elif a.cmd == "envcheck":
        import sys
        from .environments import check
        c = check()
        print(json.dumps({"env": c.env, "ok": c.ok, "problems": c.problems}, indent=2))
        sys.exit(0 if c.ok else 1)
    elif a.cmd == "ask":
        from . import db
        from .agents.knowledge_desk import ask
        with db.session() as s:
            print(json.dumps(ask(s, a.question), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
