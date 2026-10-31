import { Link } from "react-router-dom";

export function BrandMark({ light = false, to = "/dashboard" }) {
  return (
    <Link className={`brand${light ? " brand-light" : ""}`} to={to} aria-label="NagarFlow AI home">
      <span className="brand-icon" aria-hidden="true">
        <svg viewBox="0 0 32 32" fill="none">
          <path d="M5 23.5 13 8l5.2 10.1L21 13l6 10.5H5Z" fill="currentColor" />
          <path d="M4.5 26h23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </span>
      <span>Nagar<span className="brand-accent">Flow</span> <small className="brand-ai">AI</small></span>
    </Link>
  );
}

export function Field({ id, label, type, value, onChange, placeholder, autoComplete, suffix }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-wrap">
        <input
          id={id}
          name={id}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete={autoComplete}
          required
        />
        {suffix}
      </div>
    </div>
  );
}

export function PasswordToggle({ shown, onToggle }) {
  return (
    <button
      className="password-toggle"
      type="button"
      onClick={onToggle}
      aria-label={shown ? "Hide password" : "Show password"}
    >
      {shown ? "Hide" : "Show"}
    </button>
  );
}

export function SecureNote() {
  return (
    <div className="secure-note">
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.3" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" /></svg>
      {" "}Your information stays yours. Always.
    </div>
  );
}

export function WelcomeIcon() {
  return (
    <div className="welcome-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none"><path d="M4 17.5 10 6l4 7 2-3.5 4 8H4Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /><path d="M3.5 20h17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
    </div>
  );
}

export function LockIcon() {
  return (
    <div className="welcome-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none"><rect x="4.5" y="10.5" width="15" height="10" rx="2" stroke="currentColor" strokeWidth="1.7" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
    </div>
  );
}

export function MailIcon() {
  return (
    <div className="welcome-icon success-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="5.5" width="18" height="13" rx="2" stroke="currentColor" strokeWidth="1.7" /><path d="m4 7 8 6 8-6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </div>
  );
}

export function CheckIcon() {
  return (
    <div className="welcome-icon success-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.7" /><path d="m8.5 12.3 2.5 2.4 4.5-5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </div>
  );
}

export function LoadingScreen() {
  return (
    <main className="loading-screen">
      <span className="brand loading-brand">
        <span className="brand-icon" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none">
            <path d="M5 23.5 13 8l5.2 10.1L21 13l6 10.5H5Z" fill="currentColor" />
            <path d="M4.5 26h23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </span>
        <span>Nagar<span className="brand-accent">Flow</span></span>
      </span>
      <span className="loading-dot" />
    </main>
  );
}
