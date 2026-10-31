import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getCurrentUser } from "../services/api.js";

export const TOKEN_STORAGE_KEY = "nagarflow_token";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState("");

  // On first load, exchange any stored token for the current profile. This
  // is what makes a page reload keep the user signed in.
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!token) {
      setIsCheckingSession(false);
      return;
    }
    let active = true;
    getCurrentUser()
      .then((profile) => {
        if (active) setUser(profile);
      })
      .catch((error) => {
        if (!active) return;
        if (error.status === 401 || error.status === 403) {
          localStorage.removeItem(TOKEN_STORAGE_KEY);
        } else {
          setSessionError(error.message);
        }
      })
      .finally(() => {
        if (active) setIsCheckingSession(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const signIn = useCallback((accessToken, profile) => {
    localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
    setSessionError("");
    setUser(profile);
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isCheckingSession, sessionError, signIn, signOut }),
    [user, isCheckingSession, sessionError, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside an AuthProvider.");
  }
  return context;
}
