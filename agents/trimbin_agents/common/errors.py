"""Failure types.

These are distinguished because they call for different responses, and collapsing
them into one exception would lose the distinction that matters most: some
failures mean try again, and some mean the answer is genuinely "I could not tell".

An agent that cannot answer must be able to say so. A plausible guess recorded in
the archive is worse than a gap, because someone will act on it years later
without any way to know it was invented.
"""

from __future__ import annotations


class AgentError(Exception):
    """Base for everything raised inside an agent."""


class AgentFailure(AgentError):
    """The call itself failed — network, quota, malformed response.

    Retryable, up to the configured limit. After that the item is flagged and the
    batch moves on; a queue that retries forever burns credit in silence.
    """


class Unreadable(AgentError):
    """The agent looked and there was nothing to read.

    Not a failure and not retryable. A clip with no clapperboard is an ordinary
    clip — documentary and music video shoots rarely slate at all — and retrying
    will not conjure a board that was never held up. The correct response is to
    fall back to inference and mark the result uncertain.
    """


class Refused(AgentError):
    """The model declined, or returned something the schema would not accept.

    Worth separating from AgentFailure because the cause is usually the input
    rather than the infrastructure, and a retry of the same input produces the
    same refusal.
    """
