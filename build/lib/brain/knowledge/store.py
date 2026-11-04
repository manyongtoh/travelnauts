"""The company brain's knowledge: approval, review dates, cited search and the gap list.

Rules (from the proposal):
  * Agents only see approved knowledge. Proposed items wait for a specialist's approval.
  * Every item has an owner and a review date. Past the date it is flagged as possibly outdated,
    and answers built on it say so.
  * Questions the brain cannot answer, weak sources and heavily rewritten drafts become gaps.

Search here is TF-IDF so it runs offline. In production the same interface is backed by
embeddings in Postgres (pgvector); see docs/architecture.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Employee, KnowledgeGap, KnowledgeItem

# Below this score a hit is not good enough to answer from.
MIN_SCORE = 0.18

STOPWORDS_NL = ["de", "het", "een", "en", "van", "in", "is", "op", "te", "dat", "die", "voor", "met", "zijn", "we", "wij",
                "jullie", "naar", "er", "nog", "kan", "kunnen", "of", "hoe", "wat", "welke", "zit", "ook", "om", "aan",
                "bij", "als", "dan", "maar", "niet", "goed", "hallo", "beste", "groet", "alvast", "bedankt", "mensen"]


@dataclass
class Hit:
    id: str
    title: str
    body: str
    score: float
    owner: str
    review_by: date
    outdated: bool

    def cite(self) -> dict:
        return {"id": self.id, "title": self.title, "score": round(self.score, 3), "owner": self.owner,
                "review_by": self.review_by.isoformat(), "outdated": self.outdated}


class KnowledgeBase:
    def __init__(self, s: Session):
        self.s = s
        self._key = None
        self._vec = None
        self._matrix = None
        self._items: list[KnowledgeItem] = []

    def _index(self) -> None:
        items = list(self.s.scalars(select(KnowledgeItem).where(KnowledgeItem.status == "approved")).all())
        key = tuple((i.id, i.version) for i in items)
        if key == self._key:
            return
        self._items = items
        self._vec = TfidfVectorizer(stop_words=STOPWORDS_NL, ngram_range=(1, 2), sublinear_tf=True)
        docs = [f"{i.title} {i.title} {i.destination or ''} {i.body}" for i in items]
        self._matrix = self._vec.fit_transform(docs) if docs else None
        self._key = key

    def search(self, query: str, destination: str | None = None, k: int = 4) -> list[Hit]:
        self._index()
        if self._matrix is None:
            return []
        scores = cosine_similarity(self._vec.transform([query]), self._matrix)[0]
        today = date.today()
        owners = {e.id: e.name for e in self.s.scalars(select(Employee)).all()}
        hits = []
        for item, sc in zip(self._items, scores):
            if destination and item.destination not in (destination, None):
                continue
            if sc <= 0:
                continue
            hits.append(Hit(item.id, item.title, item.body, float(sc), owners.get(item.owner_id, item.owner_id),
                            item.review_by, item.review_by < today))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

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
        item.status = "approved"
        item.approved_by = approver
        item.approved_at = datetime.utcnow()
        if review_by:
            item.review_by = review_by
        self.s.commit()
        return item

    def review_due(self) -> list[KnowledgeItem]:
        return list(self.s.scalars(select(KnowledgeItem).where(KnowledgeItem.status == "approved",
                                                               KnowledgeItem.review_by < date.today())
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
