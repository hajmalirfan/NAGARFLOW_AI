import { BrandMark } from "./common.jsx";

function StoryPanel() {
  return (
    <section className="story-panel">
      <div className="story-top"><BrandMark light to="/login" /></div>
      <div className="story-copy">
        <div className="eyebrow"><span className="eyebrow-dot" /> YOUR CITY, IN FLOW</div>
        <h1>Better places<br />start with <span>better flow.</span></h1>
        <p>One thoughtful space to connect your community, simplify city life, and move good ideas forward.</p>
      </div>
      <div className="city-card" aria-hidden="true">
        <div className="city-card-top">
          <div><span className="mini-label">CITY OVERVIEW</span><strong>Good morning, city</strong></div>
          <span className="live-indicator"><i /> LIVE</span>
        </div>
        <div className="city-metrics">
          <div className="metric"><span className="metric-icon teal-icon">↗</span><strong>128</strong><small>Ideas in motion</small></div>
          <div className="metric"><span className="metric-icon gold-icon">✳</span><strong>24</strong><small>Neighborhoods</small></div>
          <div className="metric"><span className="metric-icon coral-icon">♡</span><strong>4.8k</strong><small>Active neighbors</small></div>
        </div>
        <div className="city-card-footer"><span className="avatar-stack"><i>J</i><i>M</i><i>A</i><i>+</i></span><span>Good things happen together.</span><span className="footer-spark">✳</span></div>
      </div>
      <div className="story-footer"><span>MADE FOR THE PLACES WE CALL HOME</span><span>© 2026 NAGARFLOW</span></div>
    </section>
  );
}

/** The two-panel layout shared by sign in, forgot password, and reset password. */
export default function AuthShell({ children }) {
  return (
    <main className="auth-layout">
      <StoryPanel />
      <section className="form-panel">
        <div className="mobile-brand"><BrandMark to="/login" /></div>
        <div className="form-content">{children}</div>
        <div className="form-bottom"><span>MADE FOR THE PLACES WE CALL HOME</span><a href="mailto:hello@nagarflow.local">NEED A HAND?</a></div>
      </section>
    </main>
  );
}
