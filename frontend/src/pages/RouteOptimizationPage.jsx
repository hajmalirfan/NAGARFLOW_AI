import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import ComparisonView from "../components/ComparisonView.jsx";
import ValidationReport from "../components/ValidationReport.jsx";
import { getLatestOptimization, getScenarios, optimizeScenario } from "../services/api.js";
import { PageError, PageHeading } from "./ScenarioManagementPage.jsx";

export default function RouteOptimizationPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const scenarioId = searchParams.get("scenario") ?? "";
  const [scenarios, setScenarios] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [blockedReport, setBlockedReport] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getScenarios().then(setScenarios).catch((failure) => setError(failure.message));
  }, []);

  useEffect(() => {
    setComparison(null);
    setBlockedReport(null);
    if (!scenarioId) return undefined;
    let current = true;
    getLatestOptimization(scenarioId)
      .then((result) => {
        if (current) setComparison(result);
      })
      .catch((failure) => {
        // A 404 simply means this scenario has not been run yet.
        if (current && failure.status !== 404) setError(failure.message);
      });
    return () => {
      current = false;
    };
  }, [scenarioId]);

  async function run() {
    setError("");
    setBlockedReport(null);
    setComparison(null);
    setRunning(true);
    try {
      setComparison(await optimizeScenario(scenarioId));
    } catch (failure) {
      if (failure.status === 409 && failure.report) {
        setBlockedReport(failure.report);
      } else {
        setError(failure.message);
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="OPTIMIZATION"
        title="Route Optimization"
        subtitle="Run Greedy and Google OR-Tools on identical inputs, then compare their routes."
      />
      <PageError message={error} />

      <section className="panel optimization-controls">
        <label className="scenario-field">
          <span>Scenario</span>
          <select
            value={scenarioId}
            disabled={running}
            onChange={(event) => setSearchParams(
              event.target.value ? { scenario: event.target.value } : {},
            )}
          >
            <option value="">Select a scenario</option>
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>{scenario.name}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="primary-action"
          onClick={run}
          disabled={!scenarioId || running}
        >
          {running ? "Running both algorithms…" : "Run optimization"}
        </button>
      </section>

      {blockedReport && (
        <>
          <p className="panel-note">
            Fix these problems in the <Link to={`/scenarios/${scenarioId}`}>scenario</Link>, then
            run it again.
          </p>
          <ValidationReport report={blockedReport} />
        </>
      )}

      {comparison && <ComparisonView comparison={comparison} />}
    </section>
  );
}
