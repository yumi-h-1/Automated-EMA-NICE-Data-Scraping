"""Single entry point for every model call, with retries and a size guard."""

import os
import random
import time

from openai import OpenAI

MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

# gpt-4o-mini has a 128k-token context window; ~4 chars per token leaves
# head-room for the prompt and the answer. The crawler already trims pages to
# well under this, so hitting the cap means something upstream went wrong.
MAX_INPUT_CHARS = 240_000

EXTRACTOR_SYSTEM = (
    'You are a helpful assistant who extracts complete, exact, and accurate '
    'information, especially from text.'
)
COMPARATOR_SYSTEM = (
    'You are an expert assistant who specializes in comparing medical texts and '
    'identifying therapeutic indications.'
)
SUMMARISER_SYSTEM = (
    'You write short, factual summaries of regulatory decisions for a health '
    'economics audience. You never state anything the source text does not say.'
)

_client = None


def get_client():
    """Return a cached OpenAI client, reading the key from the environment."""
    global _client
    if _client is None:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError(
                'OPENAI_API_KEY is not set. Copy .env.example to .env, or export '
                'the key before running.'
            )
        _client = OpenAI(api_key=api_key)
    return _client


def truncate(text, limit=MAX_INPUT_CHARS):
    if text is None:
        return ''
    text = str(text)
    return text if len(text) <= limit else text[:limit] + '\n[... truncated ...]'


def ask(prompt, system=EXTRACTOR_SYSTEM, attempts=3, temperature=0):
    """Send one prompt and return the reply, or 'N/A' if it could not be had."""
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
            return (response.choices[0].message.content or '').strip()
        except Exception as e:
            if attempt == attempts - 1:
                print(f'Model call failed after {attempts} attempts: {e}')
                return 'N/A'
            backoff = 2 ** attempt + random.random()
            print(f'Model call failed ({e}); retrying in {backoff:.1f}s')
            time.sleep(backoff)
    return 'N/A'
