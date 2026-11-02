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


def workspace_owner_id(user: "User") -> int:
    """Whose records this account works with: its planner's, or its own."""
    return user.planner_id or user.id
