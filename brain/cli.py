"""Command line: brain seed | serve | bench | triage | ask "question"."""
from __future__ import annotations

import argparse
import json


def main(argv: list[str] | None = None) -> None:
    import logging
    if not logging.getLogger().handlers:  # one line per event on stdout, picked up by Azure Monitor
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
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
    wk.add_argument("--once", action="store_true", help="one scheduler tick and one pass over the queue")
    wk.add_argument("--drain", action="store_true", help="work the queue until it is empty, no scheduling (scaled workers)")
    sub.add_parser("mcp", help="serve the tool server over MCP (stdio) as BRAIN_MCP_AGENT")
    sub.add_parser("reindex", help="re-read the knowledge vault")
    sub.add_parser("migrate", help="bring the database schema up to date (Alembic)")
    n8 = sub.add_parser("n8n", help="inventory of exported n8n workflows")
    n8.add_argument("paths", nargs="+")
    mc = sub.add_parser("modelcheck", help="a sample of the bench for a real model on slow hardware (test #1)")
    for flag, default in (("--mails", 30), ("--proposals", 4), ("--complaints", 3), ("--replies", 4)):
        mc.add_argument(flag, type=int, default=default)
    sub.add_parser("check", help="the morning check: open alerts (exit 2 critical, 1 warning, 0 none)")
    sub.add_parser("verify", help="row counts, audit chain and schema version (use after a restore)")
    sub.add_parser("envcheck", help="check this environment's configuration (test, pilot, live)")
    sm = sub.add_parser("simulate", help="two weeks of daily operation with incidents (clock fast-forwarded)")
    sm.add_argument("--days", type=int, default=14)
    lt = sub.add_parser("loadtest", help="many mails and several workers at once (use Postgres)")
    lt.add_argument("--mails", type=int, default=600)
    lt.add_argument("--workers", type=int, default=4)
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
        if a.drain:
            total = 0
            with db.session() as s:
                while True:
                    done = work(s, limit=50)
                    total += len(done)
                    if not done:
                        break
            print(json.dumps({"worked": total}))
        elif a.once:
            with db.session() as s:
                print(json.dumps({"scheduled": schedule_tick(s), "worked": work(s)}, indent=2, default=str))
        else:
            loop()
    elif a.cmd == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
    elif a.cmd == "migrate":
        from alembic import command
        from alembic.config import Config
        from .config import ROOT
        from pathlib import Path
        base = Path.cwd() if (Path.cwd() / "alembic.ini").exists() else ROOT
        cfg = Config(str(base / "alembic.ini"))
        cfg.set_main_option("script_location", str(base / "migrations"))
        from .ops_verify import adopt_unmanaged
        adopted = adopt_unmanaged(cfg)  # a database built without migrations is adopted only if it matches the code
        if adopted:
            print(adopted)
        command.upgrade(cfg, "head")
        print("schema up to date")
    elif a.cmd == "reindex":
        from . import db
        from .knowledge.vault import reindex
        with db.session() as s:
            print(json.dumps(reindex(s), indent=2))
    elif a.cmd == "n8n":
        from .n8n_inventory import main as n8n_main
        n8n_main(a.paths)
    elif a.cmd == "modelcheck":
        from .evals.model_check import main as mc_main
        mc_main(["--mails", str(a.mails), "--proposals", str(a.proposals), "--complaints", str(a.complaints), "--replies", str(a.replies)])
    elif a.cmd == "check":
        import sys
        from . import db as _db
        from .alerts import as_json, checks
        with _db.session() as s:
            al = as_json(checks(s))
        for x in al:
            print(f"[{x['level'].upper()}] {x['title']}: {x['detail']}\n    {x['action']}")
        print("no open alerts" if not al else f"{len(al)} open alert(s)")
        sys.exit(2 if any(x["level"] == "critical" for x in al) else 1 if al else 0)
    elif a.cmd == "verify":
        import sys
        from .ops_verify import verify_database
        r = verify_database()
        print(json.dumps(r, indent=2, default=str))
        sys.exit(0 if r["ok"] else 1)
    elif a.cmd == "envcheck":
        import sys
        from .environments import check
        c = check()
        print(json.dumps({"env": c.env, "ok": c.ok, "problems": c.problems}, indent=2))
        sys.exit(0 if c.ok else 1)
    elif a.cmd == "simulate":
        from pathlib import Path
        from .config import ROOT
        from .evals.operations import run as sim_run, to_markdown as sim_md
        rep = sim_run(a.days)
        out = ROOT / "data" / "ops"
        out.mkdir(parents=True, exist_ok=True)
        (out / "simulation.json").write_text(json.dumps(rep, indent=2, default=str))
        (out / "simulation.md").write_text(sim_md(rep))
        print(sim_md(rep))
    elif a.cmd == "loadtest":
        from .evals.load import run as load_run
        print(json.dumps(load_run(a.mails, a.workers), indent=2, default=str))
    elif a.cmd == "ask":
        from . import db
        from .agents.knowledge_desk import ask
        with db.session() as s:
            print(json.dumps(ask(s, a.question), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
