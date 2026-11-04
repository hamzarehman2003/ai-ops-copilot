"""Token counting for chunk sizes.

Embedding models limit input by tokens, not characters, so chunk sizes are measured in
tokens. `cl100k_base` (OpenAI's tokenizer) is a good general-purpose approximation; other
models' tokenizers give counts within roughly 10-20% of it.
"""

from functools import lru_cache

import tiktoken


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))
