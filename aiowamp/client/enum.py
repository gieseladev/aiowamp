from typing import NewType

__all__ = ["CancelMode", "CANCEL_SKIP", "CANCEL_KILL", "CANCEL_KILL_NO_WAIT",
           "InvocationPolicy", "INVOKE_SINGLE", "INVOKE_ROUND_ROBIN", "INVOKE_RANDOM", "INVOKE_FIRST", "INVOKE_LAST",
           "MatchPolicy", "MATCH_PREFIX", "MATCH_WILDCARD"]

CancelMode = NewType("CancelMode", str)
"""Cancel mode used to cancel a call."""
CANCEL_SKIP = CancelMode("skip")
CANCEL_KILL = CancelMode("kill")
CANCEL_KILL_NO_WAIT = CancelMode("killnowait")

InvocationPolicy = NewType("InvocationPolicy", str)
"""Invocation policy for calling a procedure."""

INVOKE_SINGLE = InvocationPolicy("single")
INVOKE_ROUND_ROBIN = InvocationPolicy("roundrobin")
INVOKE_RANDOM = InvocationPolicy("random")
INVOKE_FIRST = InvocationPolicy("first")
INVOKE_LAST = InvocationPolicy("last")

MatchPolicy = NewType("MatchPolicy", str)
"""Match policy for URIs."""

MATCH_PREFIX = MatchPolicy("prefix")
MATCH_WILDCARD = MatchPolicy("wildcard")
