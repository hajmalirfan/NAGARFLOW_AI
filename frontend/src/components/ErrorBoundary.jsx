import { Component } from "react";

/** Shows a recovery screen instead of a blank page when a page crashes. */
export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="panel" role="alert">
        <h2>This page could not be shown.</h2>
        <p className="panel-note">Your saved work is safe. Reload the page to try again.</p>
        <button type="button" className="primary-action" onClick={() => window.location.reload()}>
          Reload the page
        </button>
      </section>
    );
  }
}
