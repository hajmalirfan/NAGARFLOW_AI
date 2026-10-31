import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createScenario,
  deleteScenario,
  getScenario,
  getScenarioOptions,
  getScenarios,
  updateScenario,
} from "../services/api.js";

function PageError({ message }) {
  return message ? <p className="form-error scenario-error" role="alert">{message}</p> : null;
}

function PageHeading({ kicker, title, subtitle, action }) {
  return (
    <div className="page-head">
      <div>
        <p className="page-kicker">{kicker}</p>
        <h1>{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

function ScenarioPrerequisiteNotice({ options }) {
  const missing = [];
  if (!options.depots.length) missing.push("depots");
  if (!options.facilities.length) missing.push("processing facilities");
  if (options.vehicles.length < 2) missing.push("at least two vehicles");
  if (options.storage_points.length < 6) missing.push("at least six storage points");
  if (!missing.length) return null;
  return (
    <div className="notice">
      <strong>More setup is needed.</strong> Your database does not yet contain {missing.join(", ")}.
      Scenario choices only come from records already configured for your account; no sample records are added.
    </div>
  );
}

export function ScenarioListPage() {
  const [scenarios, setScenarios] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getScenarios()
      .then(setScenarios)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="SCENARIO MANAGEMENT"
        title="Scenarios"
        subtitle="Manage complete waste transportation planning situations."
        action={<Link className="primary-action" to="/scenarios/new">＋ Create scenario</Link>}
      />
      <PageError message={error} />
      {loading ? (
        <p className="scenario-status">Loading scenarios…</p>
      ) : scenarios.length ? (
        <div className="scenario-table-wrap">
          <table className="scenario-table">
            <thead>
              <tr><th>Scenario</th><th>Depot</th><th>Facility</th><th>Configuration</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {scenarios.map((scenario) => (
                <tr key={scenario.id}>
                  <td>
                    <Link className="scenario-name" to={`/scenarios/${scenario.id}`}>{scenario.name}</Link>
                    <span className="scenario-reference">{scenario.reference}</span>
                  </td>
                  <td>{scenario.depot?.name ?? "—"}</td>
                  <td>{scenario.processing_facility?.name ?? "—"}</td>
                  <td>{scenario.vehicles.length} vehicles · {scenario.storage_points.length} points</td>
                  <td><span className={`pill ${scenario.status === "ready" ? "pill-ok" : "pill-neutral"}`}>{scenario.status}</span></td>
                  <td><Link className="scenario-row-link" to={`/scenarios/${scenario.id}`}>View →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="panel scenario-empty">
          <h2>No scenarios yet</h2>
          <p>Create a scenario using your configured depot, processing facility, vehicles, and storage points.</p>
          <Link className="primary-action" to="/scenarios/new">Create your first scenario</Link>
        </div>
      )}
    </section>
  );
}

const EMPTY_FORM = {
  name: "",
  description: "",
  depot_id: "",
  facility_id: "",
  vehicle_ids: [],
  storage_point_ids: [],
  status: "draft",
};

function idsFromScenario(scenario) {
  return {
    name: scenario.name,
    description: scenario.description,
    depot_id: String(scenario.depot?.id ?? ""),
    facility_id: String(scenario.processing_facility?.id ?? ""),
    vehicle_ids: scenario.vehicles.map((vehicle) => String(vehicle.id)),
    storage_point_ids: scenario.storage_points.map((point) => String(point.id)),
    status: scenario.status,
  };
}

export function ScenarioFormPage() {
  const { scenarioId } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(scenarioId);
  const [options, setOptions] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      getScenarioOptions(),
      editing ? getScenario(scenarioId) : Promise.resolve(null),
    ])
      .then(([scenarioOptions, scenario]) => {
        setOptions(scenarioOptions);
        if (scenario) setForm(idsFromScenario(scenario));
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [editing, scenarioId]);

  function setField(event) {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      [name]: value,
      ...(name === "depot_id"
        ? {
            vehicle_ids: current.vehicle_ids.filter((id) =>
              options.vehicles.some(
                (vehicle) =>
                  String(vehicle.id) === id && String(vehicle.depot_id) === value,
              ),
            ),
          }
        : {}),
    }));
  }

  function toggleSelected(field, id, limit) {
    setForm((current) => {
      const selected = current[field];
      const value = String(id);
      if (selected.includes(value)) {
        return { ...current, [field]: selected.filter((item) => item !== value) };
      }
      if (selected.length >= limit) return current;
      return { ...current, [field]: [...selected, value] };
    });
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSaving(true);
    const payload = {
      ...form,
      name: form.name.trim(),
      depot_id: Number(form.depot_id),
      facility_id: Number(form.facility_id),
      vehicle_ids: form.vehicle_ids.map(Number),
      storage_point_ids: form.storage_point_ids.map(Number),
    };
    try {
      const scenario = editing
        ? await updateScenario(scenarioId, payload)
        : await createScenario(payload);
      navigate(`/scenarios/${scenario.id}`, { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setSaving(false);
    }
  }

  if (loading) return <p className="scenario-status">Loading scenario setup…</p>;
  if (!options) return <PageError message={error || "Scenario options could not be loaded."} />;

  const canSubmit = options.depots.length > 0
    && options.facilities.length > 0
    && options.vehicles.length >= 2
    && options.storage_points.length >= 6
    && form.vehicle_ids.length === 2
    && form.storage_point_ids.length >= 6
    && form.storage_point_ids.length <= 10;
  const vehiclesForDepot = options.vehicles.filter(
    (vehicle) => String(vehicle.depot_id) === form.depot_id && vehicle.is_available,
  );

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="SCENARIO MANAGEMENT"
        title={editing ? "Edit scenario" : "Create scenario"}
        subtitle="Choose configured records for this planning situation. Route optimization settings are managed separately."
      />
      <ScenarioPrerequisiteNotice options={options} />
      <PageError message={error} />
      <form className="scenario-form panel" onSubmit={submit}>
        <label className="scenario-field">
          <span>Scenario name</span>
          <input name="name" value={form.name} onChange={setField} maxLength="150" required />
        </label>
        <label className="scenario-field">
          <span>Description</span>
          <textarea name="description" value={form.description} onChange={setField} rows="3" maxLength="5000" />
        </label>
        <div className="scenario-form-grid">
          <label className="scenario-field">
            <span>Depot</span>
            <select name="depot_id" value={form.depot_id} onChange={setField} required>
              <option value="">Select a depot</option>
              {options.depots.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="scenario-field">
            <span>Processing facility</span>
            <select name="facility_id" value={form.facility_id} onChange={setField} required>
              <option value="">Select a facility</option>
              {options.facilities.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.capacity_kg.toLocaleString()} kg</option>)}
            </select>
          </label>
        </div>
        <fieldset className="scenario-selection">
          <legend>Vehicle configuration <small>{form.vehicle_ids.length}/2 selected</small></legend>
          {vehiclesForDepot.length ? vehiclesForDepot.map((vehicle) => (
            <label className={`selection-option${form.vehicle_ids.includes(String(vehicle.id)) ? " selection-option-selected" : ""}`} key={vehicle.id}>
              <input
                type="checkbox"
                checked={form.vehicle_ids.includes(String(vehicle.id))}
                disabled={!form.vehicle_ids.includes(String(vehicle.id)) && form.vehicle_ids.length >= 2}
                onChange={() => toggleSelected("vehicle_ids", vehicle.id, 2)}
              />
              <span>{vehicle.name}</span>
              <small>{vehicle.capacity_kg.toLocaleString()} kg capacity{vehicle.is_available ? "" : " · unavailable"}</small>
            </label>
          )) : <p className="scenario-help">No available vehicles are configured for the selected depot.</p>}
        </fieldset>
        <fieldset className="scenario-selection">
          <legend>Storage points <small>{form.storage_point_ids.length}/10 selected · minimum 6</small></legend>
          {options.storage_points.length ? options.storage_points.map((point) => (
            <label className={`selection-option${form.storage_point_ids.includes(String(point.id)) ? " selection-option-selected" : ""}`} key={point.id}>
              <input
                type="checkbox"
                checked={form.storage_point_ids.includes(String(point.id))}
                disabled={!form.storage_point_ids.includes(String(point.id)) && form.storage_point_ids.length >= 10}
                onChange={() => toggleSelected("storage_point_ids", point.id, 10)}
              />
              <span>{point.name}</span>
              <small>{point.waste_kg.toLocaleString()} kg{point.waste_type ? ` · ${point.waste_type}` : ""}</small>
            </label>
          )) : <p className="scenario-help">No configured storage points are available.</p>}
        </fieldset>
        <label className="scenario-field scenario-status-field">
          <span>Status</span>
          <select name="status" value={form.status} onChange={setField}>
            <option value="draft">Draft</option>
            <option value="ready">Ready</option>
          </select>
        </label>
        <div className="scenario-form-actions">
          <Link className="secondary-action" to={editing ? `/scenarios/${scenarioId}` : "/scenarios"}>Cancel</Link>
          <button className="primary-action" type="submit" disabled={saving || !canSubmit}>
            {saving ? "Saving…" : editing ? "Save changes" : "Create scenario"}
          </button>
        </div>
      </form>
    </section>
  );
}

export function ScenarioDetailPage() {
  const { scenarioId } = useParams();
  const navigate = useNavigate();
  const [scenario, setScenario] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getScenario(scenarioId)
      .then(setScenario)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [scenarioId]);

  async function removeScenario() {
    if (!window.confirm(`Delete "${scenario.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    setError("");
    try {
      await deleteScenario(scenario.id);
      navigate("/scenarios", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setDeleting(false);
    }
  }

  if (loading) return <p className="scenario-status">Loading scenario…</p>;
  if (!scenario) return <section className="scenario-page"><PageError message={error || "Scenario not found."} /><Link className="panel-link" to="/scenarios">← All scenarios</Link></section>;

  return (
    <section className="scenario-page">
      <PageHeading
        kicker={`SCENARIO MANAGEMENT · ${scenario.reference}`}
        title={scenario.name}
        subtitle={scenario.description || "No description provided."}
        action={
          <div className="scenario-actions">
            <Link className="secondary-action" to={`/scenarios/${scenario.id}/edit`}>Edit scenario</Link>
            <button type="button" className="danger-action" onClick={removeScenario} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </button>
          </div>
        }
      />
      <PageError message={error} />
      <div className="scenario-detail-grid">
        <article className="panel">
          <div className="panel-head"><h2>Planning setup</h2><span className={`pill ${scenario.status === "ready" ? "pill-ok" : "pill-neutral"}`}>{scenario.status}</span></div>
          <dl className="scenario-detail-list">
            <div><dt>Depot</dt><dd>{scenario.depot?.name ?? "Not selected"}</dd></div>
            <div><dt>Processing facility</dt><dd>{scenario.processing_facility?.name ?? "Not selected"}</dd></div>
            <div><dt>Created</dt><dd>{new Date(scenario.created_at).toLocaleDateString()}</dd></div>
            <div><dt>Last updated</dt><dd>{new Date(scenario.updated_at).toLocaleDateString()}</dd></div>
          </dl>
        </article>
        <article className="panel">
          <div className="panel-head"><h2>Vehicles</h2><span className="row-meta">{scenario.vehicles.length} selected</span></div>
          {scenario.vehicles.length ? <ul className="scenario-resource-list">{scenario.vehicles.map((vehicle) => <li key={vehicle.id}><span>{vehicle.name}</span><small>{vehicle.capacity_kg.toLocaleString()} kg capacity</small></li>)}</ul> : <p className="scenario-help">No vehicles selected.</p>}
        </article>
        <article className="panel scenario-points-panel">
          <div className="panel-head"><h2>Storage points</h2><span className="row-meta">{scenario.storage_points.length} selected</span></div>
          {scenario.storage_points.length ? <ul className="scenario-resource-list">{scenario.storage_points.map((point) => <li key={point.id}><span>{point.name}</span><small>{point.waste_kg.toLocaleString()} kg{point.waste_type ? ` · ${point.waste_type}` : ""}</small></li>)}</ul> : <p className="scenario-help">No storage points selected.</p>}
        </article>
      </div>
      <Link className="panel-link scenario-back-link" to="/scenarios">← All scenarios</Link>
    </section>
  );
}
