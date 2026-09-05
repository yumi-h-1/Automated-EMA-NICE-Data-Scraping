"""Shared configuration: HTTP headers, request timeouts and the OpenAI client."""

import os
from pathlib import Path

from openai import OpenAI

# Load .env from the repository root, whatever the working directory is — the
# notebook runs from notebooks/, the tests from the root, and scripts are called
# from both. Colab has no .env and supplies the key through os.environ instead,
# so a missing file is not an error.
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency guard
    pass
else:
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')

# EMA and NICE both serve plain HTML to a normal browser User-Agent.
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
    'DNT': '1',
    'Connection': 'keep-alive',
}

# (connect timeout, read timeout) in seconds
TIMEOUT = (10, 60)

MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

# Rough upper bound on how much text is sent to the model in one request.
# gpt-4o-mini has a 128k-token context window; ~4 chars per token leaves plenty
# of head-room for the prompt and the answer.
MAX_INPUT_CHARS = 240_000

_client = None


def get_client():
    """Return a cached OpenAI client, reading the key from the environment.

    Set the key before importing anything that calls the model, e.g.

        import os
        os.environ['OPENAI_API_KEY'] = '...'          # locally: use a .env file
        from google.colab import userdata             # in Colab
        os.environ['OPENAI_API_KEY'] = userdata.get('OPENAI_API_KEY')
    """
    global _client
    if _client is None:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError(
                'OPENAI_API_KEY is not set. Copy .env.example to .env in the project '
                'root and fill it in, or in Colab store the key as a secret and copy '
                'it into os.environ before running.'
            )
        _client = OpenAI(api_key=api_key)
    return _client
