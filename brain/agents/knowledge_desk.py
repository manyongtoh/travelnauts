"""Knowledge desk: answers questions from approved knowledge, with sources. When it cannot answer
well, it says so and puts the question on the team's gap list."""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import Draft
from ..knowledge.store import MIN_SCORE, KnowledgeBase
from ..synth.world import DESTINATIONS
from .common import audit, run_step


class Answer(BaseModel):
    answer: str
    cited: list[str]
    confident: bool


INSTRUCTIONS = (
    "Answer CONTEXT.question in Dutch using only CONTEXT.sources. Cite the ids you used. If the sources do not answer "
    "the question, set confident to false and say that you do not know yet. If a source is marked outdated, say that "
    "it needs checking."
)


def guess_destination(text: str) -> str | None:
    t = text.lower()
    for key, d in DESTINATIONS.items():
        if d["nl"].lower() in t or d["name"].lower() in t or key.replace("-", " ") in t:
            return key
    return None


def ask(s: Session, question: str, destination: str | None = None, team_id: str | None = None,
        mail_id: str | None = None) -> dict:
    kb = KnowledgeBase(s)
    destination = destination or guess_destination(question)
    with audit(s, "knowledge_desk", mail_id, question) as box:
        hits = [h for h in kb.search(question, destination, k=3) if h.score >= MIN_SCORE]
        if not hits:
            gap = kb.record_gap(question, "no_answer", destination, team_id)
            res = {"answer": "Dit weet het brein nog niet. De vraag staat op de lijst met kennishiaten voor het team.",
                   "cited": [], "confident": False, "gap_id": gap.id, "sources": []}
            box["output"] = "gap"
            return res
        ctx = {"question": question, "sources": [{"id": h.id, "title": h.title, "text": h.body, "outdated": h.outdated}
                                                  for h in hits]}
        out, _ = run_step("answer", Answer, INSTRUCTIONS, ctx)
        valid = {h.id for h in hits}
        cited = [c for c in out.cited if c in valid]
        res = out.model_dump() | {"cited": cited, "sources": [h.cite() for h in hits if h.id in cited], "gap_id": None}
        if not out.confident or not cited:
            res["gap_id"] = kb.record_gap(question, "weak_source", destination, team_id).id
        elif any(h.outdated for h in hits if h.id in cited):
            res["gap_id"] = kb.record_gap(question, "outdated", destination, team_id).id
        if mail_id:
            s.add(Draft(kind="answer", title=f"Antwoord: {question[:60]}", body=res["answer"], sources=res["sources"],
                        data={"mail_id": mail_id}))
            s.commit()
        box["sources"] = res["sources"]
        box["output"] = res["answer"][:200]
        return res
