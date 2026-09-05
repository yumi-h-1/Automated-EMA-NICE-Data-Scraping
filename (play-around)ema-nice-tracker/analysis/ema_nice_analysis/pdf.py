"""Reading the EMA procedural steps PDFs.

These are the one input the crawler cannot fetch: they are downloaded by hand
from each medicine's EPAR page, because EMA does not link them predictably.
"""

from pathlib import Path

from pypdf import PdfReader

from . import prompts
from .schema import MISSING


def extract_text(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        return '\n'.join(page.extract_text() or '' for page in reader.pages)
    except Exception as e:
        print(f'Could not read {pdf_path}: {e}')
        return ''


def find_pdf(slug, pdf_dir):
    """The procedural steps PDF for a medicine, if one was downloaded."""
    directory = Path(pdf_dir)
    if not directory.is_dir():
        return None
    return next((p for p in sorted(directory.glob('*.pdf')) if slug in p.name.lower()), None)


def indication_and_date_from_pdfs(slug, pdf_dir):
    """(most recent added indication, its Commission decision date)."""
    pdf_path = find_pdf(slug, pdf_dir)
    if pdf_path is None:
        return MISSING, MISSING

    text = extract_text(pdf_path)
    if not text:
        return MISSING, MISSING

    print(f'  reading {pdf_path.name}')
    return prompts.indication_from_pdf(text), prompts.extension_date_from_pdf(text)
