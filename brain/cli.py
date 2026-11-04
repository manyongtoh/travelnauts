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
    sub.add_parser("triage", help="triage all new mail")
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
        from .evals.bench import run, to_markdown
        print(to_markdown(run(a.seed)))
    elif a.cmd == "triage":
        from . import db
        from .agents.triage import triage_inbox
        with db.session() as s:
            for r in triage_inbox(s):
                print(r["category"], r.get("destination"), r.get("team_id"), r["summary"])
    elif a.cmd == "ask":
        from . import db
        from .agents.knowledge_desk import ask
        with db.session() as s:
            print(json.dumps(ask(s, a.question), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
