import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ComparisonView, {
  STATUS_TEXT,
  formatKm,
  formatRunDate,
} from "../components/ComparisonView.jsx";
import {
  getOptimizationBatch,
  getOptimizationHistory,
  getScenarios,
} from "../services/api.js";
import { PageError, PageHeading } from "./ScenarioManagementPage.jsx";

const PAGE_SIZE = 25;

function distanceOrStatus(status, distance) {
  return distance === null ? STATUS_TEXT[status] ?? status : formatKm(distance);
}

export function HistoryPage() {
  const [scenarios, setScenarios] = useState([]);
  const [scenarioId, setScenarioId] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getScenarios().then(setScenarios).catch((failure) => setError(failure.message));
  }, []);

  useEffect(() => {
    let current = true;
    getOptimizationHistory({
      scenario_id: scenarioId, status, limit: PAGE_SIZE, offset,
    })
      .then((result) => {
        if (current) setPage(result);
      })
      .catch((failure) => {
        if (current) setError(failure.message);
      });
    return () => {
      current = false;
    };
  }, [scenarioId, status, offset]);

  function changeFilter(setter) {
    return (event) => {
      setter(event.target.value);
      setOffset(0);
    };
  }

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="HISTORY"
        title="Optimization History"
        subtitle="Every paired run, newest first. Open one to see its saved routes."
      />
      <PageError message={error} />

      <section className="panel history-filters">
        <label className="scenario-field">
          <span>Scenario</span>
          <select value={scenarioId} onChange={changeFilter(setScenarioId)}>
            <option value="">All scenarios</option>
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>{scenario.name}</option>
            ))}
          </select>
        </label>
        <label className="scenario-field">
          <span>Status</span>
          <select value={status} onChange={changeFilter(setStatus)}>
            <option value="">All statuses</option>
            {Object.entries(STATUS_TEXT).map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </label>
      </section>

      {page?.items.length === 0 && <p className="panel-note">No optimization runs yet.</p>}

      {page?.items.length > 0 && (
        <section className="panel report-scroll">
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Scenario</th>
                <th scope="col">Greedy</th>
                <th scope="col">OR-Tools</th>
                <th scope="col">Difference</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((row) => (
                <tr key={row.batch_id}>
                  <td>{formatRunDate(row.created_at)}</td>
                  <td>
                    <Link to={`/history/${row.scenario_id}/${row.batch_id}`}>
                      {row.scenario_name}
                    </Link>
                  </td>
                  <td>{distanceOrStatus(row.greedy_status, row.greedy_distance_m)}</td>
                  <td>{distanceOrStatus(row.or_tools_status, row.or_tools_distance_m)}</td>
                  <td>{row.difference_m === null ? "" : formatKm(row.difference_m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="history-pager">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </button>
            <button
              type="button"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        </section>
      )}
    </section>
  );
}

export function HistoryRunPage() {
  const { scenarioId, batchId } = useParams();
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    getOptimizationBatch(scenarioId, batchId)
      .then((result) => {
        if (current) setComparison(result);
      })
      .catch((failure) => {
        if (current) setError(failure.message);
      });
    return () => {
      current = false;
    };
  }, [scenarioId, batchId]);

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="HISTORY"
        title="Saved run"
        subtitle="This is the result as it was saved. It does not change if the scenario does."
      />
      <PageError message={error} />
      <p className="panel-note"><Link to="/history">Back to history</Link></p>
      {comparison && <ComparisonView comparison={comparison} />}
    </section>
  );
}
