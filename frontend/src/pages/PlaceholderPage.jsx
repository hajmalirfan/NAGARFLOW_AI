import { Link } from "react-router-dom";

/**
 * A sidebar destination whose own development step has not been reached.
 *
 * It states plainly that the page is not built yet rather than showing an
 * empty shell that looks broken, or sample data that looks real.
 */
export default function PlaceholderPage({ title, kicker, step, description }) {
  return (
    <div className="placeholder-page">
      <div className="page-head">
        <div>
          <p className="page-kicker">{kicker}</p>
          <h1>{title}</h1>
          <p className="page-subtitle">{description}</p>
        </div>
      </div>
      <div className="notice">
        <strong>Not built yet.</strong> This page arrives in {step}. Nothing is shown here
        because there is no real data to show, and sample figures would be misleading.
      </div>
      <Link className="panel-link" to="/dashboard">← Back to dashboard</Link>
    </div>
  );
}
