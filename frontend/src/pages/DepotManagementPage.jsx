import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useCan } from "../auth/permissions.js";
import { createDepot, deleteDepot, getDepot, getDepots, updateDepot } from "../services/api.js";
import InputNotice from "../components/InputNotice.jsx";

function DepotError({ message }) {
  return message ? <p className="form-error depot-error" role="alert">{message}</p> : null;
}

function DepotHeading({ title, subtitle, action }) {
  return (
    <div className="page-head">
      <div>
        <p className="page-kicker">DEPOT MANAGEMENT</p>
        <h1>{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

export function DepotListPage() {
  const canWrite = useCan("records.write");
  const [depots, setDepots] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDepots()
      .then(setDepots)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="depot-page">
      <DepotHeading
        title="Depot Management"
        subtitle="Manage the municipal starting depot used by waste collection vehicles."
        action={canWrite && <Link className="primary-action" to="/depot/new">＋ Add depot</Link>}
      />
      <DepotError message={error} />
      {loading ? (
        <p className="scenario-status">Loading depots…</p>
      ) : depots.length ? (
        <div className="scenario-table-wrap">
          <table className="scenario-table">
            <thead>
              <tr><th>Depot</th><th>Address</th><th>Coordinates</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {depots.map((depot) => (
                <tr key={depot.id}>
                  <td>
                    <Link className="scenario-name" to={`/depot/${depot.id}`}>{depot.name}</Link>
                    <span className="scenario-reference">{depot.code || "Details needed"}</span>
                  </td>
                  <td>{depot.address || "—"}</td>
                  <td>{depot.latitude == null || depot.longitude == null ? "—" : `${depot.latitude}, ${depot.longitude}`}</td>
                  <td><span className={`pill ${depot.is_active ? "pill-ok" : "pill-off"}`}>{depot.is_active ? "Active" : "Inactive"}</span></td>
                  <td><Link className="scenario-row-link" to={`/depot/${depot.id}`}>View →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="panel scenario-empty">
          <h2>No depots registered</h2>
          <p>Add the depot details for this evaluation. No sample locations are created.</p>
          {canWrite && <Link className="primary-action" to="/depot/new">Add your depot</Link>}
        </div>
      )}
    </section>
  );
}

const EMPTY_DEPOT = {
  name: "",
  code: "",
  address: "",
  latitude: "",
  longitude: "",
  is_active: true,
};

export function DepotFormPage() {
  const { depotId } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(depotId);
  const [form, setForm] = useState(EMPTY_DEPOT);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [locationMessage, setLocationMessage] = useState("");

  useEffect(() => {
    if (!editing) return;
    getDepot(depotId)
      .then((depot) => setForm({
        name: depot.name,
        code: depot.code ?? "",
        address: depot.address ?? "",
        latitude: depot.latitude ?? "",
        longitude: depot.longitude ?? "",
        is_active: depot.is_active,
      }))
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [depotId, editing]);

  function setField(event) {
    const { name, value, type, checked } = event.target;
    setForm((current) => ({ ...current, [name]: type === "checkbox" ? checked : value }));
  }

  function useCurrentLocation() {
    setLocationError("");
    setLocationMessage("");
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setLocationError("Location is unavailable in this browser. Enter the coordinates manually.");
      return;
    }

    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setForm((current) => ({
          ...current,
          latitude: coords.latitude.toFixed(6),
          longitude: coords.longitude.toFixed(6),
        }));
        setLocationMessage(
          `Coordinates filled from your location (accuracy about ${Math.round(coords.accuracy)} m).`,
        );
        setLocating(false);
      },
      (locationFailure) => {
        const messages = {
          1: "Location permission was denied. Allow location access in your browser or enter coordinates manually.",
          2: "Your location could not be determined. Try again or enter coordinates manually.",
          3: "Location request timed out. Try again or enter coordinates manually.",
        };
        setLocationError(
          messages[locationFailure.code]
          ?? "Could not get your location. Enter the coordinates manually.",
        );
        setLocating(false);
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 },
    );
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload = {
      ...form,
      name: form.name.trim(),
      code: form.code.trim(),
      address: form.address.trim() || null,
      latitude: Number(form.latitude),
      longitude: Number(form.longitude),
    };
    try {
      const depot = editing
        ? await updateDepot(depotId, payload)
        : await createDepot(payload);
      navigate(`/depot/${depot.id}`, { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setSaving(false);
    }
  }

  if (loading) return <p className="scenario-status">Loading depot…</p>;

  return (
    <section className="depot-page">
      <DepotHeading
        title={editing ? "Edit depot" : "Add depot"}
        subtitle="Enter the depot details and coordinates. Only one active depot is allowed."
      />
      <InputNotice />
      <DepotError message={error} />
      <form className="scenario-form panel depot-form" onSubmit={submit}>
        <label className="scenario-field">
          <span>Depot name</span>
          <input name="name" value={form.name} onChange={setField} maxLength="150" required />
        </label>
        <label className="scenario-field">
          <span>Depot code</span>
          <input name="code" value={form.code} onChange={setField} maxLength="50" required />
        </label>
        <label className="scenario-field">
          <span>Address</span>
          <textarea name="address" value={form.address} onChange={setField} rows="3" maxLength="2000" />
        </label>
        <div className="scenario-form-grid">
          <label className="scenario-field">
            <span>Latitude</span>
            <input name="latitude" type="number" step="any" min="-90" max="90" value={form.latitude} onChange={setField} required />
          </label>
          <label className="scenario-field">
            <span>Longitude</span>
            <input name="longitude" type="number" step="any" min="-180" max="180" value={form.longitude} onChange={setField} required />
          </label>
        </div>
        <div className="depot-location-action">
          <button
            className="secondary-action"
            type="button"
            onClick={useCurrentLocation}
            disabled={locating || saving}
          >
            {locating ? "Getting your location…" : "Use my location"}
          </button>
          <span>Allow browser location access to fill both coordinates.</span>
        </div>
        {locationError && <p className="form-error" role="alert">{locationError}</p>}
        {locationMessage && <p className="depot-location-success" role="status">{locationMessage}</p>}
        <label className="depot-active-toggle">
          <input name="is_active" type="checkbox" aria-label="Active" checked={form.is_active} onChange={setField} />
          <span>Active</span>
          <small>Inactive depots cannot be selected for new or updated scenarios.</small>
        </label>
        <div className="scenario-form-actions">
          <Link className="secondary-action" to={editing ? `/depot/${depotId}` : "/depot"}>Cancel</Link>
          <button className="primary-action" type="submit" disabled={saving}>
            {saving ? "Saving…" : editing ? "Save changes" : "Add depot"}
          </button>
        </div>
      </form>
    </section>
  );
}

export function DepotDetailPage() {
  const canWrite = useCan("records.write");
  const { depotId } = useParams();
  const navigate = useNavigate();
  const [depot, setDepot] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getDepot(depotId)
      .then(setDepot)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [depotId]);

  async function removeDepot() {
    if (!window.confirm(`Delete "${depot.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    setError("");
    try {
      await deleteDepot(depot.id);
      navigate("/depot", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setDeleting(false);
    }
  }

  if (loading) return <p className="scenario-status">Loading depot…</p>;
  if (!depot) {
    return <section className="depot-page"><DepotError message={error || "Depot not found."} /><Link className="panel-link" to="/depot">← All depots</Link></section>;
  }

  return (
    <section className="depot-page">
      <DepotHeading
        title={depot.name}
        subtitle={depot.code || "Legacy depot record needs a code and coordinates."}
        action={canWrite && (
          <div className="scenario-actions">
            <Link className="secondary-action" to={`/depot/${depot.id}/edit`}>Edit depot</Link>
            <button type="button" className="danger-action" onClick={removeDepot} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </button>
          </div>
        )}
      />
      <DepotError message={error} />
      <article className="panel depot-details">
        <div className="panel-head"><h2>Depot details</h2><span className={`pill ${depot.is_active ? "pill-ok" : "pill-off"}`}>{depot.is_active ? "Active" : "Inactive"}</span></div>
        <dl className="scenario-detail-list">
          <div><dt>Depot code</dt><dd>{depot.code || "Not configured"}</dd></div>
          <div><dt>Address</dt><dd>{depot.address || "Not provided"}</dd></div>
          <div><dt>Latitude</dt><dd>{depot.latitude ?? "Not configured"}</dd></div>
          <div><dt>Longitude</dt><dd>{depot.longitude ?? "Not configured"}</dd></div>
          <div><dt>Created</dt><dd>{new Date(depot.created_at).toLocaleDateString()}</dd></div>
          <div><dt>Last updated</dt><dd>{new Date(depot.updated_at).toLocaleDateString()}</dd></div>
        </dl>
      </article>
      <Link className="panel-link scenario-back-link" to="/depot">← All depots</Link>
    </section>
  );
}
