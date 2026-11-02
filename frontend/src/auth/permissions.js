import { useAuth } from "./AuthContext.jsx";

// Mirrors backend/app/core/permissions.py. The server enforces these; here
// they only decide what a role is shown.
const SUMMARY_READERS = ["planner", "reviewer", "management"];
const READERS = ["planner", "reviewer"];

const PERMISSIONS = {
  "dashboard.read": SUMMARY_READERS,
  "records.read": READERS,
  "records.write": ["planner"],
  "optimization.read": READERS,
  "history.read": SUMMARY_READERS,
  "reports.read": SUMMARY_READERS,
  "scenarios.names": ["planner", "driver", "facility"],
  "preview.routes": ["planner", "driver"],
  "preview.facility": ["planner", "facility"],
  "team.manage": ["planner"],
};

export const ROLE_LABELS = {
  planner: "Planner",
  reviewer: "Reviewer",
  management: "Management",
  driver: "Driver preview",
  facility: "Facility preview",
};

export function can(user, permission) {
  return PERMISSIONS[permission]?.includes(user?.role) ?? false;
}

export function useCan(permission) {
  return can(useAuth().user, permission);
}

export function homePath(user) {
  if (can(user, "dashboard.read")) return "/dashboard";
  if (can(user, "scenarios.names")) return "/route-preview";
  // Settings has no permission, so an unknown role cannot loop.
  return "/settings";
}
