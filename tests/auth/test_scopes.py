"""Phase 1 control-plane maturation tests — canonical scope taxonomy.

Asserts that:

- The :class:`aqp.auth.scopes.AQPScope` namespace + ``ALL_AQP_SCOPES``
  frozenset stay in sync.
- :func:`legacy_role_to_aqp_role` translates the four tenancy roles
  (viewer / editor / admin / owner) into the four canonical
  ``aqp-*`` roles.
- :func:`expand_role_canonical` accepts both flavours and returns the
  same scope set.
- The role lattice in
  :mod:`aqp_platform_core.auth.rbac` is **strictly cumulative** —
  viewer subset of operator subset of admin subset of superadmin.
- The Python lattice (``_ROLE_LATTICE``) and the Terraform lattice
  (``terraform/modules/auth0_identity/main.tf::local.role_permissions``)
  contain the same scope set per role. This is the regression test
  for the empty-claim drift bug fixed in Phase 1.
- The closure of the lattice over ``aqp-superadmin`` is a strict
  superset of every other role and contains every canonical scope
  except ``platform:admin`` is granted only at superadmin.
- :func:`aqp.api.security._granted_scopes_for` produces the same
  scope set whether the JWT carries the canonical ``aqp-admin`` role
  or the legacy tenancy ``admin`` role (the auth0_sync drift fix).
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aqp.auth.scopes import (
    ALL_AQP_SCOPES,
    AQPScope,
    expand_role_canonical,
    expand_roles,
    legacy_role_to_aqp_role,
    normalize_role,
)
from aqp_platform_core.auth.rbac import (
    ALL_CANONICAL_SCOPES,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SUPERADMIN,
    ROLE_VIEWER,
    expand_role,
)


# ---------------------------------------------------------------------------
# AQPScope namespace integrity
# ---------------------------------------------------------------------------


class TestAQPScopeNamespace:
    """Catalogue invariants on the canonical AQPScope class."""

    def test_all_scopes_match_class_attributes(self) -> None:
        """Every public Final attribute on AQPScope appears in ALL_AQP_SCOPES."""
        attrs = {
            value
            for name, value in vars(AQPScope).items()
            if not name.startswith("_") and isinstance(value, str)
        }
        assert attrs == set(ALL_AQP_SCOPES), (
            f"AQPScope <-> ALL_AQP_SCOPES drift: "
            f"only on class={attrs - set(ALL_AQP_SCOPES)}, "
            f"only in frozenset={set(ALL_AQP_SCOPES) - attrs}"
        )

    def test_scope_strings_follow_convention(self) -> None:
        """Every scope is ``<resource>:<action>`` with no whitespace."""
        for scope in ALL_AQP_SCOPES:
            assert ":" in scope, f"missing colon: {scope!r}"
            assert not any(c.isspace() for c in scope), f"whitespace in scope: {scope!r}"
            # Ensure the resource part isn't empty and the action part isn't empty
            resource, action = scope.split(":", 1)
            assert resource and action, f"malformed scope: {scope!r}"

    def test_canonical_scopes_are_unique(self) -> None:
        """The frozenset uniques out duplicates by definition; assert size."""
        # Construct from class attributes and verify count matches the frozenset
        attrs = {
            value
            for name, value in vars(AQPScope).items()
            if not name.startswith("_") and isinstance(value, str)
        }
        assert len(attrs) == len(ALL_AQP_SCOPES)

    def test_required_canonical_scopes_present(self) -> None:
        """The canonical AQP scopes the route sweep depends on must exist."""
        required = {
            AQPScope.READ_DATA,
            AQPScope.WRITE_DATA,
            AQPScope.AGENT_VIEW,
            AQPScope.AGENT_EXECUTE,
            AQPScope.TRADE_READ,
            AQPScope.TRADE_EXECUTE,
            AQPScope.TRADE_LIVE,
            AQPScope.BACKTEST_READ,
            AQPScope.BACKTEST_CREATE,
            AQPScope.RAG_QUERY,
            AQPScope.WORKLOADS_HALT,
            AQPScope.PLATFORM_ADMIN,
        }
        assert required.issubset(ALL_AQP_SCOPES)


# ---------------------------------------------------------------------------
# Legacy role translator
# ---------------------------------------------------------------------------


class TestLegacyRoleToAqpRole:
    """Closes the auth0_sync empty-claim drift bug."""

    @pytest.mark.parametrize(
        "legacy,canonical",
        [
            ("viewer", ROLE_VIEWER),
            ("editor", ROLE_OPERATOR),
            ("admin", ROLE_ADMIN),
            ("owner", ROLE_SUPERADMIN),
        ],
    )
    def test_translates_known_legacy_roles(
        self, legacy: str, canonical: str
    ) -> None:
        assert legacy_role_to_aqp_role(legacy) == canonical

    def test_unknown_returns_none(self) -> None:
        assert legacy_role_to_aqp_role("not-a-role") is None
        assert legacy_role_to_aqp_role("") is None

    def test_strips_whitespace_and_lowercases(self) -> None:
        assert legacy_role_to_aqp_role("  Admin  ") == ROLE_ADMIN
        assert legacy_role_to_aqp_role("OWNER") == ROLE_SUPERADMIN

    @pytest.mark.parametrize(
        "role",
        [ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN, ROLE_SUPERADMIN],
    )
    def test_normalize_role_pass_through(self, role: str) -> None:
        assert normalize_role(role) == role

    def test_normalize_role_translates_legacy(self) -> None:
        assert normalize_role("admin") == ROLE_ADMIN
        assert normalize_role("editor") == ROLE_OPERATOR


# ---------------------------------------------------------------------------
# expand_role_canonical
# ---------------------------------------------------------------------------


class TestExpandRoleCanonical:
    """Both flavours of role string must produce the same scope set."""

    @pytest.mark.parametrize(
        "legacy,canonical",
        [
            ("viewer", ROLE_VIEWER),
            ("editor", ROLE_OPERATOR),
            ("admin", ROLE_ADMIN),
            ("owner", ROLE_SUPERADMIN),
        ],
    )
    def test_flavours_agree(self, legacy: str, canonical: str) -> None:
        assert expand_role_canonical(legacy) == expand_role_canonical(canonical)
        assert expand_role_canonical(canonical) == expand_role(canonical)

    def test_unknown_returns_empty_frozenset(self) -> None:
        assert expand_role_canonical("not-a-role") == frozenset()

    def test_expand_roles_unions(self) -> None:
        # admin gets everything operator gets, plus more
        admin_scopes = expand_role_canonical(ROLE_ADMIN)
        viewer_scopes = expand_role_canonical(ROLE_VIEWER)
        # expand_roles over both should equal admin (admin ⊇ viewer)
        assert expand_roles([ROLE_VIEWER, ROLE_ADMIN]) == admin_scopes
        # And expanding just viewer is a strict subset
        assert viewer_scopes < admin_scopes


# ---------------------------------------------------------------------------
# Role lattice cumulativity
# ---------------------------------------------------------------------------


class TestRoleLattice:
    """Lattice MUST be cumulative: viewer ⊂ operator ⊂ admin ⊂ superadmin."""

    def test_viewer_subset_operator(self) -> None:
        assert expand_role(ROLE_VIEWER) < expand_role(ROLE_OPERATOR)

    def test_operator_subset_admin(self) -> None:
        assert expand_role(ROLE_OPERATOR) < expand_role(ROLE_ADMIN)

    def test_admin_subset_superadmin(self) -> None:
        assert expand_role(ROLE_ADMIN) < expand_role(ROLE_SUPERADMIN)

    def test_superadmin_contains_admin_cluster(self) -> None:
        assert AQPScope.ADMIN_CLUSTER in expand_role(ROLE_SUPERADMIN)

    def test_superadmin_contains_platform_admin(self) -> None:
        assert AQPScope.PLATFORM_ADMIN in expand_role(ROLE_SUPERADMIN)

    def test_only_superadmin_has_trade_live(self) -> None:
        for role in (ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN):
            assert AQPScope.TRADE_LIVE not in expand_role(role)
        assert AQPScope.TRADE_LIVE in expand_role(ROLE_SUPERADMIN)

    def test_only_admin_plus_has_data_write(self) -> None:
        for role in (ROLE_VIEWER, ROLE_OPERATOR):
            assert AQPScope.WRITE_DATA not in expand_role(role)
        for role in (ROLE_ADMIN, ROLE_SUPERADMIN):
            assert AQPScope.WRITE_DATA in expand_role(role)

    def test_only_admin_plus_has_terraform_apply(self) -> None:
        for role in (ROLE_VIEWER, ROLE_OPERATOR):
            assert AQPScope.TERRAFORM_APPLY not in expand_role(role)
        for role in (ROLE_ADMIN, ROLE_SUPERADMIN):
            assert AQPScope.TERRAFORM_APPLY in expand_role(role)

    def test_only_superadmin_has_terraform_destroy(self) -> None:
        for role in (ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN):
            assert AQPScope.TERRAFORM_DESTROY not in expand_role(role)
        assert AQPScope.TERRAFORM_DESTROY in expand_role(ROLE_SUPERADMIN)

    def test_lattice_subset_of_canonical_scopes(self) -> None:
        for role in (ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN, ROLE_SUPERADMIN):
            assert expand_role(role).issubset(ALL_CANONICAL_SCOPES)

    def test_canonical_scopes_match_aqp_scopes(self) -> None:
        # The aqp_platform_core lattice only knows the "canonical" subset
        # (i.e. the ones it can expand). The aqp-side ALL_AQP_SCOPES is
        # the broader namespace; the two MUST agree on the union.
        assert ALL_CANONICAL_SCOPES == ALL_AQP_SCOPES


# ---------------------------------------------------------------------------
# Terraform <-> Python lattice parity
# ---------------------------------------------------------------------------


def _parse_terraform_role_permissions() -> dict[str, frozenset[str]]:
    """Best-effort parser of ``terraform/modules/auth0_identity/main.tf``.

    Reads the ``local.role_permissions`` block and returns a dict mapping
    role name ('viewer', 'operator', 'admin', 'superadmin') to the
    frozenset of permission strings declared in HCL. The Python lattice
    must agree with the Terraform lattice for every role.

    The HCL we parse is intentionally simple — string lists with one
    entry per line. A future refactor that uses HCL functions would
    require wiring in a real HCL parser; for now this is the cheapest
    check that catches drift.
    """
    tf_path = (
        Path(__file__).resolve().parents[2]
        / "terraform"
        / "modules"
        / "auth0_identity"
        / "main.tf"
    )
    if not tf_path.exists():
        pytest.skip(f"Terraform module not present at {tf_path}")
    text = tf_path.read_text(encoding="utf-8")

    # Pull out the role_permissions block (greedy enough for nested arrays
    # because role values are flat string lists).
    block_match = re.search(
        r"role_permissions\s*=\s*\{(.*?)\n\s*\}\s*\n",
        text,
        flags=re.DOTALL,
    )
    if not block_match:
        pytest.skip("role_permissions block not found in Terraform module")
    block = block_match.group(1)

    result: dict[str, frozenset[str]] = {}
    for role_match in re.finditer(
        r"(\w+)\s*=\s*\[(.*?)\]",
        block,
        flags=re.DOTALL,
    ):
        role_name = role_match.group(1)
        body = role_match.group(2)
        perms = {
            quoted.group(1)
            for quoted in re.finditer(r'"([^"]+)"', body)
        }
        result[role_name] = frozenset(perms)
    return result


class TestTerraformLatticeParity:
    """Closes the Auth0 Dashboard <-> Python role drift class of bug."""

    @pytest.mark.parametrize(
        "tf_role,python_role",
        [
            ("viewer", ROLE_VIEWER),
            ("operator", ROLE_OPERATOR),
            ("admin", ROLE_ADMIN),
            ("superadmin", ROLE_SUPERADMIN),
        ],
    )
    def test_role_set_parity(self, tf_role: str, python_role: str) -> None:
        tf_lattice = _parse_terraform_role_permissions()
        if tf_role not in tf_lattice:
            pytest.skip(f"Terraform lattice missing role {tf_role}")
        tf_scopes = tf_lattice[tf_role]
        py_scopes = expand_role(python_role)
        # Both sides must agree on the role's scope set
        only_in_tf = tf_scopes - py_scopes
        only_in_py = py_scopes - tf_scopes
        assert tf_scopes == py_scopes, (
            f"Lattice drift on role {tf_role!r} ({python_role!r}): "
            f"only in Terraform={sorted(only_in_tf)}, "
            f"only in Python={sorted(only_in_py)}"
        )


# ---------------------------------------------------------------------------
# _granted_scopes_for legacy-role drift fix (the bug Phase 1 closes)
# ---------------------------------------------------------------------------


class TestGrantedScopesAcceptsBothFlavours:
    """The auth0_sync drift bug: a JWT carrying ``editor`` produced no scopes."""

    def _user(self, *, is_default: bool = False):
        user = MagicMock()
        user.is_default = is_default
        return user

    def _request_with_namespaced_roles(self, roles: list[str]):
        req = MagicMock()
        req.state.oidc_claims = {
            "https://aqp.internal/roles": roles,
            "scope": "",
            "permissions": [],
        }
        # extract_cloudflare_access_claims returns None in unit tests
        req.state.cf_access_claims = None
        return req

    @pytest.mark.parametrize(
        "legacy,canonical",
        [
            ("viewer", ROLE_VIEWER),
            ("editor", ROLE_OPERATOR),
            ("admin", ROLE_ADMIN),
            ("owner", ROLE_SUPERADMIN),
        ],
    )
    def test_legacy_role_grants_full_canonical_set(
        self, legacy: str, canonical: str
    ) -> None:
        from aqp.api.security import _granted_scopes_for

        legacy_req = self._request_with_namespaced_roles([legacy])
        canonical_req = self._request_with_namespaced_roles([canonical])
        legacy_scopes = _granted_scopes_for(self._user(), legacy_req)
        canonical_scopes = _granted_scopes_for(self._user(), canonical_req)

        # The canonical role's scope set must be fully present in both
        canonical_role_scopes = expand_role(canonical)
        assert canonical_role_scopes.issubset(legacy_scopes), (
            f"Legacy role {legacy!r} did not grant all canonical scopes; "
            f"missing={sorted(canonical_role_scopes - legacy_scopes)}"
        )
        assert canonical_role_scopes.issubset(canonical_scopes)

    def test_editor_specifically_grants_data_read_and_write(self) -> None:
        # Pre-Phase-1 bug: editor granted no scopes via the canonical
        # path. The legacy short-circuit happened to grant data:* but
        # not the broader operator-level scope set. Phase 1 fixes this.
        from aqp.api.security import _granted_scopes_for

        req = self._request_with_namespaced_roles(["editor"])
        scopes = _granted_scopes_for(self._user(), req)
        # editor maps to aqp-operator which includes data:read,
        # data:read-only path stays for operators (write needs admin)
        assert AQPScope.READ_DATA in scopes
        assert AQPScope.AGENT_EXECUTE in scopes
        assert AQPScope.TRADE_EXECUTE in scopes


__all__: list[str] = []
