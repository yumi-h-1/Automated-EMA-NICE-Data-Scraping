"""All LLM extraction prompts in one place.

Replaces the six former query_model_for_*.py modules; the prompts are unchanged
apart from being fed trimmed input.
"""

from llm import COMPARATOR_SYSTEM, ask_model, truncate


def query_model_for_indication(html_content):
    """Full/therapeutic indication of a medicine, from its EPAR page."""
    prompt = f"""Use the HTML code provided below to answer the following question:
    Extract the full or therapeutic indication of the medicine. It may be located under the 'Overview' section or the 'Therapeutic Indication' section.

    HTML structure:
    \"\"\"
    {truncate(html_content)}
    \"\"\"

    Question: What is the full or therapeutic indication of the medicine? Write the answer in the format 'Medicine Name: Full Indication'.
    If the answer cannot be found, write only 'I don't know.'."""
    return ask_model(prompt)


def query_model_for_new_indication_html(html_content):
    """Newly added indications, marked up as bold text on a variation page."""
    prompt = f"""Use the HTML code provided below to answer the following question:
    Extract all newly added indications for the medicine. The indications are related to the patient group as well.
    The newly added indications are identified within <strong></strong> tags, indicating bold text.

    HTML structure:
    \"\"\"
    {truncate(html_content)}
    \"\"\"

    Question: What is the newly added indication of the medicine? Extract the words exactly as they appear in bold text.
    If there are different text formats between bold text sections, the first bold text is considered the first newly added indication, and any bold text that follows the different format will be the second newly added indication, and so on.
    Use a comma (',') to separate each bold text section when extracting them in order.
    Ignore boilerplate bold text such as 'First published:', 'This page was last updated on' or 'European Medicines Agency'.
    Write the answer in the format 'Medicine Name: New Indication'.
    If the answer cannot be found, write only 'I don't know.'."""
    return ask_model(prompt)


def query_model_for_removed_indication_html(html_content):
    """Removed indications, marked up as strikethrough text on a variation page."""
    prompt = f"""Use the HTML code provided below to answer the following question:
    Extract all removed indications for the medicine. The indications are related to the patient group as well.
    The removed indications are identified within <s></s> tags, indicating strikethrough text.

    HTML structure:
    \"\"\"
    {truncate(html_content)}
    \"\"\"

    Question: What is the removed indication of the medicine? Extract the words exactly as they appear in strikethrough text.
    If there are different text formats between strikethrough text sections, the first strikethrough text is considered the first removed indication, and any strikethrough text that follows the different format will be the second removed indication, and so on.
    Use a comma (',') to separate each strikethrough text section when extracting them in order.
    Write the answer in the format 'Medicine Name: Removed Indication'.
    If the answer cannot be found, write only 'I don't know.'."""
    return ask_model(prompt)


def query_model_for_new_indication_pdf(pdf_text):
    """Most recently added indication, from a procedural steps PDF."""
    prompt = f"""Use the document stored in the variable 'pdf_text' to answer the following question:
    Extract only the most recent added indication for the medicine. The date criteria is 'Commission \nDecision \nIssued2 / \namended'.
    The newly added indication may be stated between 'Extension of indication' and 'Change(s) to therapeutic indication'.

    PDF content: {truncate(pdf_text)}

    Question: What is the most recent added indication for the medicine in the variable 'pdf_text'?
    Write the answer in the format 'Medicine Name: Newly added Indication'.
    If the answer cannot be found, write 'I don't know.'."""
    return ask_model(prompt)


def query_model_for_ema_date(pdf_text):
    """Commission decision date of the most recent extension, from a PDF."""
    prompt = f"""Use the document stored in the variable 'pdf_text' to answer the following question. If the answer cannot be found, write 'N/A'.
    Extract only the most recent added indication for the medicine. The date criteria should be 'Commission \nDecision \nIssued2 / \namended'.
    The newly added indication may be stated as 'Extension of indication' or something similar.

    PDF content: {truncate(pdf_text)}

    Question: What is the commission decision issued date of the newly added indication for the medicine in the variable 'pdf_text'?
    Answer only the date in DD/MM/YYYY format."""
    return ask_model(prompt)


def query_model_for_NICE_similarity(nice_text, indication):
    """Whether a NICE page and an EMA indication describe the same indication."""
    prompt = f"""Compare the following two pieces of text and determine if they mention the same therapeutic indication for the medicine:

    NICE text:
    \"\"\"{truncate(nice_text, 60_000)}\"\"\"

    Full Indication:
    \"\"\"{truncate(indication, 20_000)}\"\"\"

    Are there any matching therapeutic indications in both texts?
    Answer only 'Yes' or 'No' and provide any matching terms if applicable.
    """
    return ask_model(prompt, system=COMPARATOR_SYSTEM)
