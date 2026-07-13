"""Mandatory bearer-token authentication with roles.

PROTOTYPE-GRADE: a static token->role map from configuration, compared with
hmac.compare_digest. This is NOT production identity/access management (no
user directory, no session revocation, no token rotation, no TLS
termination) and must never be used with real merchant data.

Token values are read from configuration and used only for comparison; they
are never logged, never returned in any response, and never stored anywhere
other than process memory.
"""

import hmac

ROLE_RANK = {"viewer": 0, "researcher": 1, "reviewer": 2, "admin": 3}


class AuthError(Exception):
    def __init__(self, message, code="unauthorized"):
        super().__init__(message)
        self.code = code


def authenticate(config, authorization_header):
    """Returns {"role": ..., "label": ...} or raises AuthError. Timing-safe."""
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise AuthError("missing bearer token")
    supplied = authorization_header[len("Bearer "):]
    for token, info in config.token_roles.items():
        if hmac.compare_digest(token, supplied) and info.get("enabled", True):
            return {"role": info["role"], "label": info["label"]}
    raise AuthError("invalid or disabled token")


def require_role(principal, minimum_role):
    """Role check by rank (admin > reviewer > researcher > viewer)."""
    if ROLE_RANK.get(principal["role"], -1) < ROLE_RANK.get(minimum_role, 99):
        raise AuthError(f"role '{principal['role']}' cannot perform an action "
                        f"requiring at least '{minimum_role}'", code="forbidden")


def require_any_role(principal, allowed_roles):
    if principal["role"] not in allowed_roles:
        raise AuthError(f"role '{principal['role']}' is not permitted "
                        f"(requires one of: {', '.join(allowed_roles)})", code="forbidden")


def safe_token_introspection(config):
    """For an admin introspection endpoint: label + role + enabled status ONLY.
    Never returns the token itself or any reusable hash of it."""
    return [{"label": info["label"], "role": info["role"], "enabled": info.get("enabled", True)}
            for info in config.token_roles.values()]
