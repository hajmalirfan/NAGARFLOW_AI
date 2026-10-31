import { Navigate, Outlet, useLocation } from "react-router-dom";
import { LoadingScreen } from "../components/common.jsx";
import { useAuth } from "./AuthContext.jsx";

/**
 * Guards every signed-in page.
 *
 * While the stored token is being checked it shows the loading screen, so
 * a reload does not flash the login page. If there is no session it sends
 * the visitor to /login and remembers where they were heading.
 */
export default function ProtectedRoute() {
  const { user, isCheckingSession } = useAuth();
  const location = useLocation();

  if (isCheckingSession) {
    return <LoadingScreen />;
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
