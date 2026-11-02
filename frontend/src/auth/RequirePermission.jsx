import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";
import { can, homePath } from "./permissions.js";

/** Sends a role away from a page it cannot use. The server still enforces it. */
export default function RequirePermission({ permission }) {
  const { user } = useAuth();
  return can(user, permission) ? <Outlet /> : <Navigate to={homePath(user)} replace />;
}
