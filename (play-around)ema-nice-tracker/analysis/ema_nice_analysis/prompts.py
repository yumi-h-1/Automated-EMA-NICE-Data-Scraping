"""Every prompt the pipeline sends, in one place."""

from .llm import COMPARATOR_SYSTEM, SUMMARISER_SYSTEM, ask, truncate


def full_indication(indication_html):
    """The therapeutic indication, copied verbatim off an EPAR page."""
    return ask(f"""Use the HTML code provided below to answer the following question:
Extract the full or therapeutic indication of the medicine. It may be located under the 'Overview' section or the 'Therapeutic Indication' section.

HTML structure:
\"\"\"
{truncate(indication_html)}
\"\"\"

Question: What is the full or therapeutic indication of the medicine? Copy the wording exactly as it appears; do not paraphrase.
Write the answer in the format 'Medicine Name: Full Indication'.
If the answer cannot be found, write only 'I don't know.'.""")


def new_indication(variation_html):
    """Newly added indications, marked up as bold text on a variation page."""
    return ask(f"""Use the HTML code provided below to answer the following question:
Extract all newly added indications for the medicine. The indications are related to the patient group as well.
The newly added indications are identified within <strong></strong> tags, indicating bold text.

HTML structure:
\"\"\"
{truncate(variation_html)}
\"\"\"

Question: What is the newly added indication of the medicine? Extract the words exactly as they appear in bold text.
If there are different text formats between bold text sections, the first bold text is the first newly added indication, and any bold text that follows a different format is the second, and so on.
Use a comma (',') to separate each bold text section when extracting them in order.
Ignore boilerplate bold text such as 'First published:', 'This page was last updated on' or 'European Medicines Agency'.
Write the answer in the format 'Medicine Name: New Indication'.
If the answer cannot be found, write only 'I don't know.'.""")


def removed_indication(variation_html):
    """Removed indications, marked up as strikethrough text."""
    return ask(f"""Use the HTML code provided below to answer the following question:
Extract all removed indications for the medicine. The indications are related to the patient group as well.
The removed indications are identified within <s></s> tags, indicating strikethrough text.

HTML structure:
\"\"\"
{truncate(variation_html)}
\"\"\"

Question: What is the removed indication of the medicine? Extract the words exactly as they appear in strikethrough text.
Use a comma (',') to separate each strikethrough text section when extracting them in order.
Write the answer in the format 'Medicine Name: Removed Indication'.
If the answer cannot be found, write only 'I don't know.'.""")


def indication_from_pdf(pdf_text):
    """Most recently added indication, from a procedural steps PDF."""
    return ask(f"""Use the document below to answer the following question:
Extract only the most recently added indication for the medicine. The date criteria is 'Commission Decision Issued / amended'.
The newly added indication may be stated between 'Extension of indication' and 'Change(s) to therapeutic indication'.

PDF content: {truncate(pdf_text)}

Question: What is the most recently added indication for the medicine?
Write the answer in the format 'Medicine Name: Newly added Indication'.
If the answer cannot be found, write 'I don't know.'.""")


def extension_date_from_pdf(pdf_text):
    """Commission decision date of the most recent extension."""
    return ask(f"""Use the document below to answer the following question. If the answer cannot be found, write 'N/A'.
Find the most recently added indication for the medicine. The date criteria is 'Commission Decision Issued / amended'.
The newly added indication may be stated as 'Extension of indication' or something similar.

PDF content: {truncate(pdf_text)}

Question: What is the Commission decision issued date of the newly added indication?
Answer only the date in DD/MM/YYYY format.""")


def nice_similarity(nice_text, indication):
    """Whether a NICE page and an EMA indication describe the same indication."""
    return ask(
        f"""Compare the following two pieces of text and determine if they mention the same therapeutic indication for the medicine:

NICE text:
\"\"\"{truncate(nice_text, 60_000)}\"\"\"

Full Indication:
\"\"\"{truncate(indication, 20_000)}\"\"\"

Are there any matching therapeutic indications in both texts?
Answer only 'Yes' or 'No' and provide any matching terms if applicable.""",
        system=COMPARATOR_SYSTEM,
    )


def change_summary(product_name, recommendation, full_indication_text, added, removed):
    """One or two sentences saying what this meeting actually changed.

    EMA marks indication changes as a character-level diff, so the raw bold and
    strikethrough fragments read as 'A', 'an', '-based regimen'. This turns them
    back into a sentence a person can read, using only what the page says.
    """
    added_text = '; '.join(added) if added else '(none)'
    removed_text = '; '.join(removed) if removed else '(none)'

    return ask(
        f"""A medicine received a positive CHMP opinion. Write one or two plain sentences saying what changed.

Medicine: {product_name}
Kind of recommendation: {recommendation}
Full therapeutic indication: \"\"\"{truncate(full_indication_text, 20_000)}\"\"\"
Text EMA marked as ADDED: \"\"\"{truncate(added_text, 8_000)}\"\"\"
Text EMA marked as REMOVED: \"\"\"{truncate(removed_text, 8_000)}\"\"\"

The added and removed fragments come from a character-level diff, so they may be
sentence fragments. Read them together with the full indication to work out the change.

Rules:
- State only what these texts support. Do not add clinical background, trial
  results, comparisons, or anything about other medicines.
- Name the disease, the patient population and the line of therapy only if the
  texts give them.
- If it is a first authorisation, say what the medicine is approved to treat.
- If the texts do not support any statement, write exactly 'Not stated'.
- No preamble. Just the sentences.""",
        system=SUMMARISER_SYSTEM,
    )
