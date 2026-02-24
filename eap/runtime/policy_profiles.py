from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple

from eap.runtime.auth_scopes import (
    FULL_RUNTIME_SCOPES,
    SCOPE_POINTERS_READ,
    SCOPE_POINTERS_READ_ANY,
    SCOPE_RUNS_EXECUTE,
    SCOPE_RUNS_READ,
    SCOPE_RUNS_READ_ANY,
    SCOPE_RUNS_RESUME,
    SCOPE_RUNS_RESUME_ANY,
)

DEFAULT_POLICY_PROFILE = "strict"
SUPPORTED_POLICY_PROFILES = {"strict", "balanced", "trusted"}

_PROFILE_ALLOWED_SCOPES: Dict[str, Set[str]] = {
    "strict": {
        SCOPE_RUNS_EXECUTE,
        SCOPE_RUNS_RESUME,
        SCOPE_RUNS_READ,
        SCOPE_POINTERS_READ,
        SCOPE_RUNS_READ_ANY,
        SCOPE_POINTERS_READ_ANY,
    },
    "balanced": set(FULL_RUNTIME_SCOPES),
    "trusted": set(FULL_RUNTIME_SCOPES) | {"*"},
}

_PROFILE_TEMPLATES: Dict[str, Dict[str, Set[str]]] = {
    "strict": {
        "viewer": {SCOPE_RUNS_READ, SCOPE_POINTERS_READ},
        "operator": {SCOPE_RUNS_EXECUTE, SCOPE_RUNS_RESUME, SCOPE_RUNS_READ, SCOPE_POINTERS_READ},
        "auditor": {SCOPE_RUNS_READ, SCOPE_POINTERS_READ, SCOPE_RUNS_READ_ANY, SCOPE_POINTERS_READ_ANY},
        "admin": {SCOPE_RUNS_READ, SCOPE_POINTERS_READ, SCOPE_RUNS_READ_ANY, SCOPE_POINTERS_READ_ANY},
    },
    "balanced": {
        "viewer": {SCOPE_RUNS_READ, SCOPE_POINTERS_READ},
        "operator": {SCOPE_RUNS_EXECUTE, SCOPE_RUNS_RESUME, SCOPE_RUNS_READ, SCOPE_POINTERS_READ},
        "auditor": {SCOPE_RUNS_READ, SCOPE_POINTERS_READ, SCOPE_RUNS_READ_ANY, SCOPE_POINTERS_READ_ANY},
        "admin": set(FULL_RUNTIME_SCOPES),
    },
    "trusted": {
        "viewer": {SCOPE_RUNS_READ, SCOPE_POINTERS_READ},
        "operator": {SCOPE_RUNS_EXECUTE, SCOPE_RUNS_RESUME, SCOPE_RUNS_READ, SCOPE_POINTERS_READ},
        "auditor": {SCOPE_RUNS_READ, SCOPE_POINTERS_READ, SCOPE_RUNS_READ_ANY, SCOPE_POINTERS_READ_ANY},
        "admin": {"*"},
    },
}


def resolve_policy_profile_name(value: str | None) -> str:
    profile = (value or DEFAULT_POLICY_PROFILE).strip().lower()
    if profile not in SUPPORTED_POLICY_PROFILES:
        supported = ", ".join(sorted(SUPPORTED_POLICY_PROFILES))
        raise ValueError(f"Unsupported policy profile '{value}'. Expected one of: {supported}.")
    return profile


def _parse_scopes(value: Any) -> List[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _validate_scopes_for_profile(
    scopes: Iterable[str],
    *,
    profile: str,
    token_label: str,
) -> Set[str]:
    allowed_scopes = _PROFILE_ALLOWED_SCOPES[profile]
    normalized: Set[str] = set()
    for scope in scopes:
        if scope not in FULL_RUNTIME_SCOPES and scope != "*":
            raise ValueError(
                f"Token '{token_label}' requested unknown scope '{scope}'. "
                f"Use runtime scopes or '*'."
            )
        if scope not in allowed_scopes:
            raise ValueError(
                f"Token '{token_label}' requested scope '{scope}' disallowed by profile '{profile}'."
            )
        normalized.add(scope)
    return normalized


def build_scoped_token_policies(
    payload: Dict[str, Any],
    *,
    default_policy_profile: str = DEFAULT_POLICY_PROFILE,
) -> Tuple[Dict[str, Dict[str, Any]], str]:
    tokens_payload = payload.get("tokens")
    if not isinstance(tokens_payload, list):
        raise ValueError("scoped auth config must include a 'tokens' array.")

    base_profile = resolve_policy_profile_name(payload.get("policy_profile") or default_policy_profile)
    normalized: Dict[str, Dict[str, Any]] = {}

    for index, item in enumerate(tokens_payload):
        if not isinstance(item, dict):
            raise ValueError(f"Token entry #{index} must be a JSON object.")

        token = str(item.get("token", "")).strip()
        actor_id = str(item.get("actor_id", "")).strip()
        token_label = token or f"entry#{index}"
        if not token:
            raise ValueError(f"Token entry #{index} is missing required field 'token'.")
        if not actor_id:
            raise ValueError(f"Token '{token_label}' is missing required field 'actor_id'.")

        profile = resolve_policy_profile_name(item.get("policy_profile") or base_profile)
        template = str(item.get("template", "")).strip().lower()
        explicit_scopes = _parse_scopes(item.get("scopes"))

        effective_scopes: Set[str] = set()
        if template:
            template_scopes = _PROFILE_TEMPLATES[profile].get(template)
            if template_scopes is None:
                supported_templates = ", ".join(sorted(_PROFILE_TEMPLATES[profile]))
                raise ValueError(
                    f"Token '{token_label}' requested unknown template '{template}' for profile "
                    f"'{profile}'. Supported templates: {supported_templates}."
                )
            effective_scopes.update(template_scopes)
        effective_scopes.update(explicit_scopes)
        effective_scopes = _validate_scopes_for_profile(
            effective_scopes,
            profile=profile,
            token_label=token_label,
        )
        if not effective_scopes:
            raise ValueError(
                f"Token '{token_label}' resolves to zero scopes. "
                "Deny-by-default is active; provide a template and/or scopes."
            )

        auth_subject = str(item.get("auth_subject", "")).strip() or f"scoped_token:{profile}:{actor_id}"
        token_policy: Dict[str, Any] = {
            "actor_id": actor_id,
            "auth_subject": auth_subject,
            "scopes": sorted(effective_scopes),
            "policy_profile": profile,
        }
        if template:
            token_policy["template"] = template
        normalized[token] = token_policy

    return normalized, base_profile


def describe_policy_profile_matrix() -> Dict[str, Dict[str, List[str]]]:
    return {
        profile: {
            template: sorted(scopes)
            for template, scopes in sorted(_PROFILE_TEMPLATES[profile].items())
        }
        for profile in sorted(_PROFILE_TEMPLATES)
    }

