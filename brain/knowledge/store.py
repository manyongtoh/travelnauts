"""The company brain's knowledge: approval, review dates, hybrid search with roles, gaps, semantic cache.

Rules (from the architecture):
  * Agents only see approved, current knowledge. Proposed items wait for approval; archived policy
    versions stay for audits but are never returned.
  * Every item has an owner and a review date. Past the date it is flagged as possibly outdated.
  * Search combines keyword and meaning (reciprocal rank fusion), filtered by the caller's role.
  * Questions the brain cannot answer, weak sources and heavily rewritten drafts become gaps.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import CacheEntry, Employee, KnowledgeGap, KnowledgeItem, cache_put
from .embed import embedder
from ..clock import utcnow
from ..clock import today as clock_today

MIN_SCORE = 0.18  # keyword score below which a hit is not good enough to answer from
STOPWORDS_NL = ["de", "het", "een", "en", "van", "in", "is", "op", "te", "dat", "die", "voor", "met", "zijn", "we", "wij",
                "jullie", "naar", "er", "nog", "kan", "kunnen", "of", "hoe", "wat", "welke", "zit", "ook", "om", "aan",
                "bij", "als", "dan", "maar", "niet", "goed", "hallo", "beste", "groet", "alvast", "bedankt", "mensen",
                "the", "a", "an", "to", "of", "is", "when", "what", "how", "for", "with", "and", "best"]
_INDEX: dict = {}


@dataclass
class Hit:
    id: str
    title: str
    body: str
    score: float
    owner: str
    review_by: date
    outdated: bool
    source: str | None = None
    vector_score: float = 0.0

    def cite(self) -> dict:
        return {"id": self.id, "title": self.title, "score": round(self.score, 3), "owner": self.owner,
                "review_by": self.review_by.isoformat(), "outdated": self.outdated, "source": self.source}


def searchable(today: date | None = None):
    today = today or clock_today()
    return select(KnowledgeItem).where(KnowledgeItem.status == "approved", KnowledgeItem.topic != "house_rule",
                                       (KnowledgeItem.valid_from.is_(None)) | (KnowledgeItem.valid_from <= today),
                                       (KnowledgeItem.valid_to.is_(None)) | (KnowledgeItem.valid_to >= today))


class KnowledgeBase:
    def __init__(self, s: Session):
        self.s = s

    def _index(self) -> dict:
        items = list(self.s.scalars(searchable()).all())
        key = hashlib.sha256("|".join(f"{i.id}:{i.version}:{i.content_hash}" for i in items).encode()).hexdigest()
        if _INDEX.get("key") == key:
            return _INDEX
        docs = [f"{i.title} {i.title} {i.destination or ''} {i.body}" for i in items]
        _INDEX.clear()
        _INDEX.update(key=key, items=items, ids=[i.id for i in items])
        if docs:
            _INDEX["vec"] = TfidfVectorizer(stop_words=STOPWORDS_NL, ngram_range=(1, 2), sublinear_tf=True)
            _INDEX["matrix"] = _INDEX["vec"].fit_transform(docs)
            _INDEX["emb"] = embedder().fit(docs)
            from .concepts import topics
            _INDEX["topics"] = [topics(f"{i.title} {i.body}") | set(i.tags or []) for i in items]
        return _INDEX

    def search(self, query: str, destination: str | None = None, k: int = 4, role: str | None = None) -> list[Hit]:
        idx = self._index()
        if not idx.get("ids"):
            return []
        from .concepts import destination_in, expand, topics
        items = {i.id: i for i in self.s.scalars(select(KnowledgeItem).where(KnowledgeItem.id.in_(idx["ids"]))).all()}
        q = expand(query)  # the question plus words that mean the same ("omboeken" also searches "wijzigen")
        kw = cosine_similarity(idx["vec"].transform([q]), idx["matrix"])[0]
        vs = idx["emb"].scores(q)
        q_dest = destination or destination_in(query)  # "Bali" is Indonesia: a boost, never a filter
        q_topics = topics(query)
        owners = {e.id: e.name for e in self.s.scalars(select(Employee)).all()}
        kw_max = max(float(kw.max()), 1e-6)
        today = clock_today()
        hits = []
        for j, iid in enumerate(idx["ids"]):
            item = items.get(iid)
            if item is None or (destination and item.destination not in (destination, None)):
                continue
            if role and role not in (item.roles or []):
                continue
            if kw[j] <= 0 and vs[j] < 0.35 and not (q_topics & idx["topics"][j] - {"kids"} and q_dest == item.destination):
                continue
            fused = 0.7 * kw[j] / kw_max + 0.3 * max(vs[j], 0)  # keyword leads; meaning catches spelling and word forms
            if q_dest and item.destination == q_dest:
                fused += 0.15
            shared = q_topics & idx["topics"][j]
            fused += 0.1 * min(len(shared - {"kids"}), 2)  # same topic (season, lodging, entry, ...): a small push
            hits.append((fused, Hit(item.id, item.title, item.body, float(kw[j]), owners.get(item.owner_id, item.owner_id),
                                    item.review_by, item.review_by < today, item.source, float(vs[j]))))
        hits.sort(key=lambda x: -x[0])
        return [h for _, h in hits[:k]]

    # Approval flow -------------------------------------------------------------------------
    def propose(self, item_id: str, title: str, body: str, owner_id: str, destination: str | None, topic: str,
                review_by: date) -> KnowledgeItem:
        item = KnowledgeItem(id=item_id, title=title, body=body, owner_id=owner_id, destination=destination, topic=topic,
                             status="proposed", review_by=review_by)
        self.s.add(item)
        self.s.commit()
        return item

    def approve(self, item_id: str, approver: str, review_by: date | None = None) -> KnowledgeItem:
        item = self.s.get(KnowledgeItem, item_id)
        if item is None:
            raise KeyError(item_id)
        if item.pending_body is not None:  # approving a change: the new text becomes the approved text
            item.body, item.content_hash, item.version = item.pending_body, item.pending_hash, item.version + 1
            item.pending_body = item.pending_hash = None
        item.status = "approved"
        item.approved_by = approver
        item.approved_at = utcnow()
        if review_by:
            item.review_by = review_by
        elif item.review_by < clock_today():
            item.review_by = clock_today() + timedelta(days=180)
        clear_semantic_cache(self.s)
        self.s.commit()
        return item

    def review_due(self) -> list[KnowledgeItem]:
        return list(self.s.scalars(select(KnowledgeItem).where(KnowledgeItem.status == "approved",
                                                               KnowledgeItem.review_by < clock_today())
                                   .order_by(KnowledgeItem.review_by)).all())

    # Gaps ----------------------------------------------------------------------------------
    def record_gap(self, question: str, reason: str, destination: str | None = None, team_id: str | None = None) -> KnowledgeGap:
        q = question.strip()
        existing = self.s.scalars(select(KnowledgeGap).where(KnowledgeGap.question == q, KnowledgeGap.status == "open")).first()
        if existing:
            existing.count += 1
            self.s.commit()
            return existing
        gap = KnowledgeGap(question=q, reason=reason, destination=destination, team_id=team_id)
        self.s.add(gap)
        self.s.commit()
        return gap

    def gaps(self, team_id: str | None = None) -> list[KnowledgeGap]:
        q = select(KnowledgeGap).where(KnowledgeGap.status == "open")
        if team_id:
            q = q.where(KnowledgeGap.team_id == team_id)
        return list(self.s.scalars(q.order_by(KnowledgeGap.count.desc(), KnowledgeGap.created_at)).all())


# Semantic cache: only for internal knowledge questions, never anything with customer data ----------

def semantic_lookup(s: Session, question: str, role: str | None, threshold: float = 0.92) -> dict | None:
    rows = [c for c in s.scalars(select(CacheEntry).where(CacheEntry.kind == "semantic")).all() if c.expires_at > utcnow()
            and (c.value or {}).get("role") == role]
    if not rows:
        return None
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit([question] + [r.text for r in rows])
    sims = cosine_similarity(vec.transform([question]), vec.transform([r.text for r in rows]))[0]
    best = max(range(len(rows)), key=lambda i: sims[i])
    return rows[best].value["answer"] if sims[best] >= threshold else None


def semantic_store(s: Session, question: str, role: str | None, answer: dict, hours: int = 24) -> None:
    key = "semantic:" + hashlib.sha256(f"{role}|{question.lower().strip()}".encode()).hexdigest()
    cache_put(s, key, "semantic", {"role": role, "answer": answer}, utcnow() + timedelta(hours=hours), text=question)


def clear_semantic_cache(s: Session) -> None:
    s.query(CacheEntry).filter(CacheEntry.kind == "semantic").delete()
