# -*- coding: utf-8 -*-

"""
Structural auth-guard test for the Phase C user routes (M7/M8a; PhaseC §6).

Asserts that EVERY endpoint in kiro/routes_user.py declares a user-auth-enforcing
dependency in its dependency tree — replacing "convention + review" with a test,
so a future route cannot be added unguarded.

The acceptable guards are an allowlist of the auth/authz dependencies. In this
codebase the auth dependencies are plain ``async def f(request)`` that call each
other directly (not via nested ``Depends``), so a route's FastAPI dependant graph
shows only the single top-level dependency it declared. Each allowlisted guard is
independently unit-tested (test_supabase_dependencies.py) to authenticate first:
  - require_supabase_user  — authenticates (M7);
  - get_auth_state         — authenticates + enforces DB user-state (M8a);
  - get_current_user_profile — get_auth_state + profile body (M8a);
  - require_onboarded      — get_current_user_profile + onboarding gate (M8a).
A route declaring any one of these is guaranteed to enforce authentication.

Structural: inspects the resolved dependant graph; runs no endpoint.
"""

from fastapi.routing import APIRoute

from kiro.routes_user import router
from kiro.supabase_auth.dependencies import (
    get_auth_state,
    get_current_user_profile,
    require_onboarded,
    require_supabase_user,
)

# Any one of these in a route's dependant tree enforces authentication.
_AUTH_GUARDS = frozenset({
    require_supabase_user,
    get_auth_state,
    get_current_user_profile,
    require_onboarded,
})


def _all_dependency_calls(dependant):
    """Recursively collect every `.call` in a dependant's subtree."""
    calls = []
    for dep in dependant.dependencies:
        calls.append(dep.call)
        calls.extend(_all_dependency_calls(dep))
    return calls


def _api_routes():
    return [r for r in router.routes if isinstance(r, APIRoute)]


def test_router_has_routes():
    # Guard against a vacuous pass if the router were empty.
    assert len(_api_routes()) >= 2


def test_every_user_route_declares_auth_dependency():
    offenders = []
    for route in _api_routes():
        calls = set(_all_dependency_calls(route.dependant))
        if calls.isdisjoint(_AUTH_GUARDS):
            offenders.append(f"{sorted(route.methods)} {route.path}")
    assert not offenders, (
        "These routes_user endpoints declare no auth-enforcing dependency: "
        + ", ".join(offenders)
    )
