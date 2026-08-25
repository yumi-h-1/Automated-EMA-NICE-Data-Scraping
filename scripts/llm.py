"""Single entry point for every model call, with retries and a size guard."""

import random
import time

from config import MAX_INPUT_CHARS, MODEL, get_client

EXTRACTOR_SYSTEM = (
    'You are a helpful assistant who extracts complete, exact, and accurate '
    'information, especially from text.'
)

COMPARATOR_SYSTEM = (
    'You are an expert assistant who specializes in comparing medical texts and '
    'identifying therapeutic indications.'
)


def truncate(text, limit=MAX_INPUT_CHARS):
    """Clip oversized page text so a request cannot blow the context window."""
    if text is None:
        return ''
    if len(text) <= limit:
        return text
    return text[:limit] + '\n[... truncated ...]'


def ask_model(prompt, system=EXTRACTOR_SYSTEM, attempts=3, temperature=0):
    """Send one prompt to the model and return the reply, or 'N/A' on failure.

    Retries transient errors (rate limits, timeouts) with exponential backoff.
    """
    client = get_client()
    for attempt in range(attempts):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                temperature=temperature,
                messages=[
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': prompt},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if attempt == attempts - 1:
                print(f'Error querying the model: {e}')
                return 'N/A'
            backoff = 2 ** attempt + random.random()
            print(f'Model call failed ({e}); retrying in {backoff:.1f}s')
            time.sleep(backoff)
    return 'N/A'
