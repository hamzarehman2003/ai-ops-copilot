"""What the retriever searches for.

A follow-up question is often elliptical ("And on Enterprise?", "How do I fix it?"): searched
on its own it matches nothing, or the wrong thing, and the copilot abstains. So in a
conversation the previous question is prepended to the search text. The model still sees the
user's exact question; only retrieval gets the extra context.

Why this and not an LLM rewrite ("condense the conversation into a standalone question"): it
is deterministic, free, works in offline mode, and adds no latency. A rewrite handles topic
switches and pronouns better, at the cost of one more model call per follow-up; it is the
next step if the follow-up eval cases show this baseline missing.
"""


def search_query(question: str, previous_questions: list[str]) -> str:
    if not previous_questions:
        return question
    return f"{previous_questions[-1]}\n{question}"
