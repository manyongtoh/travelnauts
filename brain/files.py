"""Where documents live: attachments, generated roadbooks and vouchers. Blob Storage in Azure."""
from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT


def files_dir() -> Path:
    p = Path(os.getenv("BRAIN_FILES", str(ROOT / "data" / "files")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def pdf_text(path: str | Path) -> str:
    from pypdf import PdfReader
    return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)


def simple_pdf(path: Path, title: str, lines: list[str]) -> Path:
    """A plain PDF, used for synthetic partner offers."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, y, title)
    c.setFont("Helvetica", 11)
    for line in lines:
        y -= 18
        c.drawString(60, y, line)
    c.save()
    return path
