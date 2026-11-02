"""Roles, and the workspace an account belongs to.

Roles are the proposed views from the requirements document, not municipal
job titles. Their real authority is unconfirmed.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User

ROLE_PLANNER = "planner"
ROLE_REVIEWER = "reviewer"
ROLE_MANAGEMENT = "management"
ROLE_DRIVER = "driver"
ROLE_FACILITY = "facility"

_ALL = frozenset({ROLE_PLANNER, ROLE_REVIEWER, ROLE_MANAGEMENT, ROLE_DRIVER, ROLE_FACILITY})
_PLANNER = frozenset({ROLE_PLANNER})
_READERS = frozenset({ROLE_PLANNER, ROLE_REVIEWER})
_SUMMARY_READERS = frozenset({ROLE_PLANNER, ROLE_REVIEWER, ROLE_MANAGEMENT})

PERMISSIONS: dict[str, frozenset[str]] = {
    "account": _ALL,
    "dashboard.read": _SUMMARY_READERS,
    "records.read": _READERS,
    "records.write": _PLANNER,
    "optimization.read": _READERS,
    "history.read": _SUMMARY_READERS,
    "reports.read": _SUMMARY_READERS,
    "scenarios.names": frozenset({ROLE_PLANNER, ROLE_DRIVER, ROLE_FACILITY}),
    "preview.routes": frozenset({ROLE_PLANNER, ROLE_DRIVER}),
    "preview.facility": frozenset({ROLE_PLANNER, ROLE_FACILITY}),
    "team.manage": _PLANNER,
}


def workspace_owner_id(user: "User") -> int:
    """Whose records this account works with: its planner's, or its own."""
    return user.planner_id or user.id
