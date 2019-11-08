import aiowamp

__all__ = ["CLIENT_ROLES"]

CLIENT_ROLES: aiowamp.WAMPDict
"""WAMP roles/features for the aiowamp client."""

CLIENT_ROLES = {
    "publisher": {
        "features": {
            "subscriber_blackwhite_listing": True,
            "publisher_exclusion": True,
            "publisher_identification": True,
        },
    },
    "subscriber": {
        "features": {
            "publisher_identification": True,
            "publication_trustlevels": True,
            "pattern_based_subscription": True,
            "sharded_subscription": True,  # TODO maybe?
            "event_history": True,
            "subscription_revocation": True,  # TODO
        },
    },
    "callee": {
        "features": {
            "progressive_call_results": True,
            "call_timeout": True,  # TODO
            "call_canceling": True,
            "caller_identification": True,
            "call_trustlevels": True,
            "pattern_based_registration": True,
            "shared_registration": True,
            "sharded_registration": True,  # TODO maybe not
            "registration_revocation": True,  # TODO
        },
    },
    "caller": {
        "features": {
            "progressive_call_results": True,
            "call_timeout": True,
            "call_canceling": True,
            "caller_identification": True,
        },
    },
}
