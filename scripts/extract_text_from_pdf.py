"""Text extraction from the EMA procedural steps PDFs.

Uses pypdf; PyPDF2 was retired in 2023 and no longer installs on current Python.
"""

from pypdf import PdfReader


def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        return '\n'.join(page.extract_text() or '' for page in reader.pages)
    except Exception as e:
        print(f'Error processing {pdf_path}: {e}')
        return ''
