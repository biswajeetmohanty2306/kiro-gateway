# -*- coding: utf-8 -*-

"""
Structural auth-guard test for the Phase C user routes (M7; canonical PhaseC §6).

Asserts that EVERY endpoint in kiro/routes_user.py declares the user-auth
dependency (require_supabase_user) in its dependency tree — replacing
"convention + review" with a test, so a future route cannot be added unguarded.

This is structural: it inspects the FastAPI route's resolved dependant graph, it
does not call any endpoint or run the app.
"""

from fastapi.routing import APIRoute

from kiro.routes_user import router
from kiro.supabase_auth.dependencies import require_supabase_user


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
        calls = _all_dependency_calls(route.dependant)
        if require_supabase_user not in calls:
            offenders.append(f"{sorted(route.methods)} {route.path}")
    assert not offenders, (
        "These routes_user endpoints lack require_supabase_user: " + ", ".join(offenders)
    )
