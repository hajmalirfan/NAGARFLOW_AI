import { useState } from "react";
import { Link } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import { Field, LockIcon, MailIcon, SecureNote } from "../components/common.jsx";
import { forgotPassword } from "../services/api.js";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sentTo, setSentTo] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    const address = email.trim();

    try {
      await forgotPassword(address);
      setSentTo(address);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  if (sentTo) {
    return (
      <AuthShell>
        <MailIcon />
        <p className="form-kicker">CHECK YOUR INBOX</p>
        <h2>Check your email.</h2>
        <p className="form-subtitle">
          If an account exists for <strong>{sentTo}</strong>, we have sent a password reset
          link to it. The link works once and expires in 15 minutes.
        </p>
        <div className="info-panel">
          <p>Nothing in your inbox? Check your spam folder, then request a new link.</p>
        </div>
        <Link className="submit-button" to="/login">
          Back to login<span aria-hidden="true">→</span>
        </Link>
        <p className="form-switch">
          Wrong email address?{" "}
          <button type="button" onClick={() => setSentTo("")}>Try another</button>
        </p>
        <SecureNote />
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <LockIcon />
      <p className="form-kicker">PASSWORD HELP</p>
      <h2>Forgot your password?</h2>
      <p className="form-subtitle">
        Enter the email address for your account and we will send you a link to choose a
        new password.
      </p>

      <form onSubmit={handleSubmit}>
        <Field
          id="email"
          label="Email address"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
        />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="submit-button" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Sending…" : "Send reset link"}
          {!isSubmitting && <span aria-hidden="true">→</span>}
        </button>
      </form>

      <p className="form-switch">
        Remembered it? <Link to="/login">Back to login</Link>
      </p>
      <SecureNote />
    </AuthShell>
  );
}
