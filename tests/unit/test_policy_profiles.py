import unittest

from eap.runtime.auth_scopes import (
    SCOPE_POINTERS_READ,
    SCOPE_POINTERS_READ_ANY,
    SCOPE_RUNS_EXECUTE,
    SCOPE_RUNS_READ,
    SCOPE_RUNS_READ_ANY,
    SCOPE_RUNS_RESUME,
    SCOPE_RUNS_RESUME_ANY,
)
from eap.runtime.policy_profiles import (
    DEFAULT_POLICY_PROFILE,
    build_scoped_token_policies,
    resolve_policy_profile_name,
)


class PolicyProfilesUnitTest(unittest.TestCase):
    def test_resolve_policy_profile_defaults_to_strict(self) -> None:
        self.assertEqual(resolve_policy_profile_name(None), DEFAULT_POLICY_PROFILE)

    def test_build_scoped_token_policies_supports_template_profiles(self) -> None:
        scoped, profile = build_scoped_token_policies(
            {
                "policy_profile": "balanced",
                "tokens": [
                    {"token": "viewer-token", "actor_id": "viewer", "template": "viewer"},
                    {"token": "admin-token", "actor_id": "admin", "template": "admin"},
                ],
            }
        )
        self.assertEqual(profile, "balanced")
        self.assertEqual(
            scoped["viewer-token"]["scopes"],
            sorted({SCOPE_RUNS_READ, SCOPE_POINTERS_READ}),
        )
        self.assertEqual(
            scoped["admin-token"]["scopes"],
            sorted(
                {
                    SCOPE_RUNS_EXECUTE,
                    SCOPE_RUNS_RESUME,
                    SCOPE_RUNS_READ,
                    SCOPE_POINTERS_READ,
                    SCOPE_RUNS_RESUME_ANY,
                    SCOPE_RUNS_READ_ANY,
                    SCOPE_POINTERS_READ_ANY,
                }
            ),
        )

    def test_trusted_admin_template_maps_to_wildcard_scope(self) -> None:
        scoped, profile = build_scoped_token_policies(
            {
                "policy_profile": "trusted",
                "tokens": [{"token": "admin-token", "actor_id": "admin", "template": "admin"}],
            }
        )
        self.assertEqual(profile, "trusted")
        self.assertEqual(scoped["admin-token"]["scopes"], ["*"])

    def test_strict_profile_rejects_disallowed_scope(self) -> None:
        with self.assertRaises(ValueError):
            build_scoped_token_policies(
                {
                    "policy_profile": "strict",
                    "tokens": [
                        {
                            "token": "operator-token",
                            "actor_id": "op",
                            "template": "operator",
                            "scopes": [SCOPE_RUNS_RESUME_ANY],
                        }
                    ],
                }
            )

    def test_rejects_unknown_template_for_profile(self) -> None:
        with self.assertRaises(ValueError):
            build_scoped_token_policies(
                {
                    "policy_profile": "strict",
                    "tokens": [{"token": "bad-token", "actor_id": "op", "template": "super-admin"}],
                }
            )


if __name__ == "__main__":
    unittest.main()

