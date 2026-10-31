import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";
import AuthShell from "../components/AuthShell.jsx";
import { CheckIcon, Field, LockIcon, PasswordToggle, SecureNote } from "../components/common.jsx";
import { resetPassword, verifyResetToken } from "../services/api.js";

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState("verifying");
  const [accountEmail, setAccountEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("This password reset link is missing its token. Request a new one.");
      setStatus("invalid");
      return;
    }
    let active = true;
    verifyResetToken(token)
      .then((result) => {
        if (!active) return;
        setAccountEmail(result.email);
        setStatus("form");
      })
      .catch((verifyError) => {
        if (!active) return;
        setError(verifyError.message);
        setStatus("invalid");
      });
    return () => {
      active = false;
    };
  }, [token]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("Your new password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Both passwords must match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await resetPassword(token, password);
      // Changing the password ends any existing session on this device.
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setStatus("done");
    } catch (requestError) {
      setError(requestError.message);
      if (requestError.status === 400) {
        setStatus("invalid");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (status === "verifying") {
    return (
      <AuthShell>
        <LockIcon />
        <p className="form-kicker">PASSWORD RESET</p>
        <h2>Checking your link…</h2>
        <p className="form-subtitle">One moment while we make sure this reset link is still valid.</p>
        <span className="loading-dot" />
      </AuthShell>
    );
  }

  if (status === "invalid") {
    return (
      <AuthShell>
        <LockIcon />
        <p className="form-kicker">PASSWORD RESET</p>
        <h2>This link no longer works.</h2>
        <p className="form-subtitle">{error}</p>
        <div className="info-panel">
          <p>Reset links expire after 15 minutes and can only be used once. Request a fresh one from the login page.</p>
        </div>
        <Link className="submit-button" to="/forgot-password">
          Request a new link<span aria-hidden="true">→</span>
        </Link>
        <p className="form-switch">
          <Link to="/login">Back to login</Link>
        </p>
        <SecureNote />
      </AuthShell>
    );
  }

  if (status === "done") {
    return (
      <AuthShell>
        <CheckIcon />
        <p className="form-kicker">ALL SET</p>
        <h2>Password updated.</h2>
        <p className="form-subtitle">
          Your password has been changed. Sign in with your new password to get back to
          your city.
        </p>
        <Link className="submit-button" to="/login">
          Back to login<span aria-hidden="true">→</span>
        </Link>
        <SecureNote />
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <LockIcon />
      <p className="form-kicker">PASSWORD RESET</p>
      <h2>Choose a new password.</h2>
      <p className="form-subtitle">
        You are resetting the password for <strong>{accountEmail}</strong>.
      </p>

      <form onSubmit={handleSubmit}>
        <Field
          id="password"
          label="New password"
          type={showPassword ? "text" : "password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="At least 8 characters"
          autoComplete="new-password"
          suffix={<PasswordToggle shown={showPassword} onToggle={() => setShowPassword(!showPassword)} />}
        />
        <Field
          id="confirmPassword"
          label="Confirm new password"
          type={showPassword ? "text" : "password"}
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          placeholder="Type it once more"
          autoComplete="new-password"
        />
        {error && <p className="form-error" role="alert">{error}</p>}
        <p className="password-hint">Use at least 8 characters for a stronger password.</p>
        <button className="submit-button" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Updating…" : "Update password"}
          {!isSubmitting && <span aria-hidden="true">→</span>}
        </button>
      </form>

      <p className="form-switch">
        Changed your mind? <Link to="/login">Back to login</Link>
      </p>
      <SecureNote />
    </AuthShell>
  );
}
