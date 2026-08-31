"""Failure types.

These are distinguished because they call for different responses, and collapsing
them into one exception would lose the distinction that matters most: some
failures mean try again, and some mean the answer is genuinely "I could not tell".

An agent that cannot answer must be able to say so. A plausible guess recorded in
the archive is worse than a gap, because someone will act on it years later
without any way to know it was invented.
"""

from __future__ import annotations

from typing import Protocol


class _HasText(Protocol):
    # A read-only property, not a settable attribute: every SDK response type
    # computes `text` from its candidates, and a Protocol declaring a variable
    # will not accept one.
    @property
    def text(self) -> str | None: ...


class AgentError(Exception):
    """Base for everything raised inside an agent."""


class AgentFailure(AgentError):
    """The call itself failed — network, quota, malformed response.

    Retryable, up to the configured limit. After that the item is flagged and the
    batch moves on; a queue that retries forever burns credit in silence.
    """


def text_of(response: _HasText, what: str) -> str:
    """The model's answer, or a failure that says which agent got nothing.

    Every caller used `response.text` directly, which is typed `str | None` and
    is None whenever the model produced no candidate. This is the one place that
    turns absence into a sentence somebody can act on.
    """
    text: str | None = getattr(response, "text", None)
    if not text or not text.strip():
        raise Empty(f"{what} returned no text")
    return text


class Unreadable(AgentError):
    """The agent looked and there was nothing to read.

    Not a failure and not retryable. A clip with no clapperboard is an ordinary
    clip — documentary and music video shoots rarely slate at all — and retrying
    will not conjure a board that was never held up. The correct response is to
    fall back to inference and mark the result uncertain.
    """


class Empty(AgentError):
    """The call succeeded and the model said nothing.

    `response.text` is `str | None` on every Gemini call, and it is None more
    often than it looks: a safety block, an empty candidate list, a stop before
    the first token. Five call sites passed it straight into
    `model_validate_json`, where None becomes a TypeError raised from inside
    pydantic — so the log said the schema was wrong when the truth was that
    there was no answer at all.

    Separated from Refused because the cause is usually transient and the input
    is usually fine.
    """


class Refused(AgentError):
    """The model declined, or returned something the schema would not accept.

    Worth separating from AgentFailure because the cause is usually the input
    rather than the infrastructure, and a retry of the same input produces the
    same refusal.
    """
