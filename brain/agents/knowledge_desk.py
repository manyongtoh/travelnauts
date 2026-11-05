"""Knowledge desk: answers questions from approved knowledge, with sources. When it cannot answer
well, it says so and puts the question on the team's gap list."""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Draft
from ..identity import agent
from ..knowledge.store import MIN_SCORE, KnowledgeBase
from ..toolserver import server
from .common import audit, run_step

ME = agent("knowledge_desk")


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
    from ..knowledge.concepts import destination_in
    return destination_in(text)  # also "Bali", "Zanzibar", "Kaapstad"


def ask(s: Session, question: str, destination: str | None = None, team_id: str | None = None,
        mail_id: str | None = None, role: str | None = None) -> dict:
    from ..knowledge.store import semantic_lookup, semantic_store
    kb = KnowledgeBase(s)
    destination = destination or guess_destination(question)
    if not mail_id:  # internal questions only: never anything with customer data
        cached = semantic_lookup(s, question, role)
        if cached:
            return cached | {"cached": True}
    with audit(s, "knowledge_desk", mail_id, question) as box:
        hits = [h for h in server.call(s, ME, "knowledge.search", query=question, destination=destination, k=3, role=role)
                if h["score"] >= MIN_SCORE]
        if not hits:
            gap = kb.record_gap(question, "no_answer", destination, team_id)
            res = {"answer": "Dit weet het brein nog niet. De vraag staat op de lijst met kennishiaten voor het team.",
                   "cited": [], "confident": False, "gap_id": gap.id, "sources": []}
            if mail_id:  # a family is waiting: give the specialist a blank answer; what they write teaches the brain
                _answer_draft(s, mail_id, "[Schrijf hier het antwoord. Het brein wist dit nog niet: jouw antwoord wordt een "
                                          "voorstel voor de kennisbank.]", [], gap.id)
            box["output"] = "gap"
            return res
        ctx = {"question": question, "sources": [{"id": h["id"], "title": h["title"], "text": h["body"], "outdated": h["outdated"]}
                                                  for h in hits]}
        out, _ = run_step(s, "answer", Answer, INSTRUCTIONS, ctx)
        valid = {h["id"] for h in hits}
        cite = lambda h: {k: v for k, v in h.items() if k != "body"}
        cited = [c for c in out.cited if c in valid]
        res = out.model_dump() | {"cited": cited, "sources": [cite(h) for h in hits if h["id"] in cited], "gap_id": None}
        if not out.confident or not cited:
            res["gap_id"] = kb.record_gap(question, "weak_source", destination, team_id).id
        elif any(h["outdated"] for h in hits if h["id"] in cited):
            res["gap_id"] = kb.record_gap(question, "outdated", destination, team_id).id
        if not mail_id and res["confident"] and not res["gap_id"]:
            semantic_store(s, question, role, res)
        if mail_id:
            _answer_draft(s, mail_id, res["answer"], res["sources"], res["gap_id"])
        box["sources"] = res["sources"]
        box["output"] = res["answer"][:200]
        return res



def _answer_draft(s: Session, mail_id: str, body: str, sources: list, gap_id: int | None) -> Draft:
    """The answer goes to the specialist on the family's latest trip, so it shows up in their own list."""
    from ..db import Mail, TripRequest
    m = s.get(Mail, mail_id)
    tr = s.scalars(select(TripRequest).where(TripRequest.family_id == m.family_id).order_by(TripRequest.created_at.desc())).first() \
        if m and m.family_id else None
    d = Draft(kind="answer", request_id=tr.id if tr else None, title=f"Antwoord: {(m.subject if m else '')[:60]}", body=body,
              sources=sources, data={"mail_id": mail_id, "gap_id": gap_id, "team_id": tr.team_id if tr else None})
    s.add(d)
    s.commit()
    return d
