import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import AuthShell from "../components/AuthShell.jsx";
import { Field, PasswordToggle, SecureNote, WelcomeIcon } from "../components/common.jsx";
import { login, register } from "../services/api.js";

export default function SignInPage() {
  const { user, signIn, sessionError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(sessionError);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isRegistering = mode === "register";

  // Already signed in? Go where they were heading, or the dashboard.
  if (user) {
    return <Navigate to={location.state?.from ?? "/dashboard"} replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const result = isRegistering
        ? await register({ name: name.trim(), email: email.trim(), password })
        : await login({ email: email.trim(), password });
      signIn(result.access_token, result.user);
      navigate(location.state?.from ?? "/dashboard", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setIsSubmitting(false);
    }
  }

  function changeMode(nextMode) {
    setMode(nextMode);
    setError("");
    setPassword("");
  }

  return (
    <AuthShell>
      <WelcomeIcon />
      <p className="form-kicker">{isRegistering ? "A LITTLE CLOSER TO YOUR CITY" : "WELCOME BACK TO YOUR CITY"}</p>
      <h2>{isRegistering ? "Create your account" : "Good to see you."}</h2>
      <p className="form-subtitle">{isRegistering ? "Join your neighbors and get good things moving." : "Sign in to pick up where your community left off."}</p>

      <div className="auth-tabs" role="group" aria-label="Account options">
        <button type="button" aria-pressed={!isRegistering} className={!isRegistering ? "active" : ""} onClick={() => changeMode("login")}>Sign in</button>
        <button type="button" aria-pressed={isRegistering} className={isRegistering ? "active" : ""} onClick={() => changeMode("register")}>Create account</button>
      </div>

      <form onSubmit={handleSubmit}>
        {isRegistering && (
          <Field id="name" label="Full name" type="text" value={name} onChange={(event) => setName(event.target.value)} placeholder="How should we call you?" autoComplete="name" />
        )}
        <Field id="email" label="Email address" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" autoComplete="email" />
        <Field
          id="password"
          label="Password"
          type={showPassword ? "text" : "password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder={isRegistering ? "At least 8 characters" : "Enter your password"}
          autoComplete={isRegistering ? "new-password" : "current-password"}
          suffix={<PasswordToggle shown={showPassword} onToggle={() => setShowPassword(!showPassword)} />}
        />
        {!isRegistering && (
          <div className="forgot-row">
            <Link className="link-button" to="/forgot-password">Forgot password?</Link>
          </div>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}
        {isRegistering && <p className="password-hint">Use at least 8 characters for a stronger password.</p>}
        <button className="submit-button" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Please wait…" : isRegistering ? "Create your account" : "Sign in"}
          {!isSubmitting && <span aria-hidden="true">→</span>}
        </button>
      </form>

      <p className="form-switch">
        {isRegistering ? "Already part of the neighborhood?" : "New to NagarFlow?"}{" "}
        <button type="button" onClick={() => changeMode(isRegistering ? "login" : "register")}>{isRegistering ? "Sign in" : "Create an account"}</button>
      </p>
      <SecureNote />
    </AuthShell>
  );
}
