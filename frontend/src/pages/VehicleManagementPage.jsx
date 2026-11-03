import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useCan } from "../auth/permissions.js";
import InputNotice from "../components/InputNotice.jsx";
import {
  createVehicle,
  deleteVehicle,
  getDepots,
  getVehicle,
  getVehicles,
  updateVehicle,
} from "../services/api.js";

function VehicleError({ message }) {
  return message ? <p className="form-error vehicle-error" role="alert">{message}</p> : null;
}

function VehicleHeading({ title, subtitle, action }) {
  return (
    <div className="page-head">
      <div>
        <p className="page-kicker">FLEET MANAGEMENT</p>
        <h1>{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

export function VehicleListPage() {
  const canWrite = useCan("records.write");
  const [vehicles, setVehicles] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getVehicles()
      .then(setVehicles)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="vehicle-page">
      <VehicleHeading
        title="Vehicle Management"
        subtitle="Manage the two collection vehicles and their starting depot."
        action={canWrite && <Link className="primary-action" to="/vehicles/new">＋ Add vehicle</Link>}
      />
      <VehicleError message={error} />
      {loading ? (
        <p className="scenario-status">Loading vehicles…</p>
      ) : vehicles.length ? (
        <div className="scenario-table-wrap">
          <table className="scenario-table">
            <thead>
              <tr><th>Vehicle</th><th>Type</th><th>Capacity</th><th>Depot</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {vehicles.map((vehicle) => (
                <tr key={vehicle.id}>
                  <td>
                    <Link className="scenario-name" to={`/vehicles/${vehicle.id}`}>{vehicle.name}</Link>
                    <span className="scenario-reference">{vehicle.vehicle_number || "Registration needed"}</span>
                  </td>
                  <td>{vehicle.vehicle_type || "—"}</td>
                  <td>{vehicle.capacity_kg.toLocaleString()} kg</td>
                  <td>{vehicle.depot?.name || "—"}</td>
                  <td><span className={`pill ${vehicle.status === "available" ? "pill-ok" : vehicle.status === "maintenance" ? "pill-neutral" : "pill-off"}`}>{vehicle.status}</span></td>
                  <td><Link className="scenario-row-link" to={`/vehicles/${vehicle.id}`}>View →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="panel scenario-empty">
          <h2>No vehicles registered</h2>
          <p>Register the two vehicles with their registration, capacity and depot.</p>
          {canWrite && <Link className="primary-action" to="/vehicles/new">Add first vehicle</Link>}
        </div>
      )}
    </section>
  );
}

const EMPTY_VEHICLE = {
  vehicle_number: "",
  name: "",
  vehicle_type: "Truck",
  capacity_kg: "",
  depot_id: "",
  status: "available",
};

export function VehicleFormPage() {
  const { vehicleId } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(vehicleId);
  const [form, setForm] = useState(EMPTY_VEHICLE);
  const [depots, setDepots] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      getDepots(),
      editing ? getVehicle(vehicleId) : Promise.resolve(null),
    ])
      .then(([allDepots, vehicle]) => {
        setDepots(allDepots.filter((depot) => depot.is_active && depot.latitude != null && depot.longitude != null));
        if (vehicle) {
          setForm({
            vehicle_number: vehicle.vehicle_number ?? "",
            name: vehicle.name,
            vehicle_type: vehicle.vehicle_type ?? "Truck",
            capacity_kg: vehicle.capacity_kg,
            depot_id: String(vehicle.depot?.id ?? ""),
            status: vehicle.status,
          });
        }
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [editing, vehicleId]);

  function setField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload = {
      ...form,
      vehicle_number: form.vehicle_number.trim(),
      name: form.name.trim(),
      capacity_kg: Number(form.capacity_kg),
      depot_id: Number(form.depot_id),
    };
    try {
      const vehicle = editing
        ? await updateVehicle(vehicleId, payload)
        : await createVehicle(payload);
      navigate(`/vehicles/${vehicle.id}`, { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setSaving(false);
    }
  }

  if (loading) return <p className="scenario-status">Loading vehicle setup…</p>;

  return (
    <section className="vehicle-page">
      <VehicleHeading
        title={editing ? "Edit vehicle" : "Add vehicle"}
        subtitle="Register a vehicle and assign it to the active starting depot."
      />
      <InputNotice />
      {!depots.length && (
        <div className="notice"><strong>An active depot is required.</strong> Configure a depot with coordinates before adding vehicles. <Link to="/depot">Manage depots</Link></div>
      )}
      <VehicleError message={error} />
      <form className="scenario-form panel vehicle-form" onSubmit={submit}>
        <label className="scenario-field">
          <span>Vehicle number</span>
          <input name="vehicle_number" value={form.vehicle_number} onChange={setField} maxLength="30" required />
        </label>
        <label className="scenario-field">
          <span>Vehicle name</span>
          <input name="name" value={form.name} onChange={setField} maxLength="100" required />
        </label>
        <label className="scenario-field">
          <span>Vehicle type</span>
          <select name="vehicle_type" value={form.vehicle_type} onChange={setField}>
            <option value="Truck">Truck</option>
            <option value="Mini Truck">Mini Truck</option>
          </select>
        </label>
        <label className="scenario-field">
          <span>Capacity (kg)</span>
          <input name="capacity_kg" type="number" step="0.01" min="0.01" value={form.capacity_kg} onChange={setField} required />
        </label>
        <label className="scenario-field">
          <span>Depot</span>
          <select name="depot_id" value={form.depot_id} onChange={setField} required>
            <option value="">Select a depot</option>
            {depots.map((depot) => <option key={depot.id} value={depot.id}>{depot.name}</option>)}
          </select>
        </label>
        <label className="scenario-field">
          <span>Status</span>
          <select name="status" value={form.status} onChange={setField}>
            <option value="available">Available</option>
            <option value="maintenance">Maintenance</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
        <div className="scenario-form-actions">
          <Link className="secondary-action" to={editing ? `/vehicles/${vehicleId}` : "/vehicles"}>Cancel</Link>
          <button className="primary-action" type="submit" disabled={saving || !depots.length}>
            {saving ? "Saving…" : editing ? "Save changes" : "Add vehicle"}
          </button>
        </div>
      </form>
    </section>
  );
}

export function VehicleDetailPage() {
  const canWrite = useCan("records.write");
  const { vehicleId } = useParams();
  const navigate = useNavigate();
  const [vehicle, setVehicle] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getVehicle(vehicleId)
      .then(setVehicle)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [vehicleId]);

  async function removeVehicle() {
    if (!window.confirm(`Delete "${vehicle.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    setError("");
    try {
      await deleteVehicle(vehicle.id);
      navigate("/vehicles", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setDeleting(false);
    }
  }

  if (loading) return <p className="scenario-status">Loading vehicle…</p>;
  if (!vehicle) {
    return <section className="vehicle-page"><VehicleError message={error || "Vehicle not found."} /><Link className="panel-link" to="/vehicles">← All vehicles</Link></section>;
  }

  return (
    <section className="vehicle-page">
      <VehicleHeading
        title={vehicle.name}
        subtitle={vehicle.vehicle_number || "Legacy vehicle record needs registration details."}
        action={canWrite && (
          <div className="scenario-actions">
            <Link className="secondary-action" to={`/vehicles/${vehicle.id}/edit`}>Edit vehicle</Link>
            <button type="button" className="danger-action" onClick={removeVehicle} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </button>
          </div>
        )}
      />
      <VehicleError message={error} />
      <article className="panel vehicle-details">
        <div className="panel-head"><h2>Vehicle details</h2><span className={`pill ${vehicle.status === "available" ? "pill-ok" : vehicle.status === "maintenance" ? "pill-neutral" : "pill-off"}`}>{vehicle.status}</span></div>
        <dl className="scenario-detail-list">
          <div><dt>Vehicle number</dt><dd>{vehicle.vehicle_number || "Not configured"}</dd></div>
          <div><dt>Vehicle type</dt><dd>{vehicle.vehicle_type || "Not configured"}</dd></div>
          <div><dt>Capacity</dt><dd>{vehicle.capacity_kg.toLocaleString()} kg</dd></div>
          <div><dt>Starting depot</dt><dd>{vehicle.depot?.name || "Not configured"}</dd></div>
          <div><dt>Created</dt><dd>{new Date(vehicle.created_at).toLocaleDateString()}</dd></div>
          <div><dt>Last updated</dt><dd>{new Date(vehicle.updated_at).toLocaleDateString()}</dd></div>
        </dl>
      </article>
      <Link className="panel-link scenario-back-link" to="/vehicles">← All vehicles</Link>
    </section>
  );
}
