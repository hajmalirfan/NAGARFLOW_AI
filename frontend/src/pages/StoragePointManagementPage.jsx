import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import StoragePointMap from "../components/StoragePointMap.jsx";
import {
  createStoragePoint,
  deleteStoragePoint,
  getStoragePoint,
  getStoragePoints,
  updateStoragePoint,
} from "../services/api.js";

function StoragePointError({ message }) {
  return message ? <p className="form-error storage-point-error" role="alert">{message}</p> : null;
}

function StoragePointHeading({ title, subtitle, action }) {
  return (
    <div className="page-head">
      <div>
        <p className="page-kicker">COLLECTION POINTS</p>
        <h1>{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

const EMPTY_STORAGE_POINT = {
  name: "",
  point_code: "",
  address: "",
  latitude: "",
  longitude: "",
  waste_quantity_kg: "",
  availability_status: "available",
  available_from: "",
  description: "",
};

function StoragePointFilters({ search, setSearch, availability, setAvailability }) {
  return (
    <div className="storage-point-filters">
      <label>
        <span>Search storage points</span>
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search by name, code, or address"
        />
      </label>
      <label>
        <span>Availability</span>
        <select value={availability} onChange={(event) => setAvailability(event.target.value)}>
          <option value="all">All statuses</option>
          <option value="available">Available</option>
          <option value="unavailable">Unavailable</option>
        </select>
      </label>
    </div>
  );
}

export function StoragePointListPage() {
  const [points, setPoints] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [availability, setAvailability] = useState("all");

  useEffect(() => {
    getStoragePoints()
      .then(setPoints)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const filteredPoints = useMemo(() => {
    const query = search.trim().toLowerCase();
    return points.filter((point) => {
      const matchesSearch = !query
        || [point.name, point.point_code, point.address ?? ""]
          .some((value) => value.toLowerCase().includes(query));
      const matchesAvailability = availability === "all"
        || point.availability_status === availability;
      return matchesSearch && matchesAvailability;
    });
  }, [availability, points, search]);

  return (
    <section className="storage-point-page">
      <StoragePointHeading
        title="Storage Point Management"
        subtitle="Manage real collection locations, recorded waste quantities, and availability."
        action={<Link className="primary-action" to="/storage-points/new">＋ Add storage point</Link>}
      />
      <StoragePointError message={error} />
      <StoragePointMap points={filteredPoints} />
      <StoragePointFilters
        search={search}
        setSearch={setSearch}
        availability={availability}
        setAvailability={setAvailability}
      />
      {loading ? (
        <p className="scenario-status">Loading storage points…</p>
      ) : filteredPoints.length ? (
        <div className="scenario-table-wrap">
          <table className="scenario-table">
            <thead>
              <tr><th>Storage point</th><th>Address</th><th>Coordinates</th><th>Waste</th><th>Availability</th><th /></tr>
            </thead>
            <tbody>
              {filteredPoints.map((point) => (
                <tr key={point.id}>
                  <td>
                    <Link className="scenario-name" to={`/storage-points/${point.id}`}>{point.name}</Link>
                    <span className="scenario-reference">{point.point_code}</span>
                  </td>
                  <td>{point.address || "—"}</td>
                  <td>{point.latitude}, {point.longitude}</td>
                  <td>{Number(point.waste_quantity_kg).toLocaleString()} kg</td>
                  <td>
                    <span className={`pill ${point.availability_status === "available" ? "pill-ok" : "pill-off"}`}>
                      {point.availability_status}
                    </span>
                  </td>
                  <td><Link className="scenario-row-link" to={`/storage-points/${point.id}`}>View →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="panel scenario-empty">
          <h2>{points.length ? "No matching storage points" : "No storage points registered"}</h2>
          <p>
            {points.length
              ? "Try a different search or availability filter."
              : "Register actual collection points. No sample locations or waste values are created."}
          </p>
          {!points.length && <Link className="primary-action" to="/storage-points/new">Add your first point</Link>}
        </div>
      )}
      {!loading && points.length > 0 && (
        <p className="storage-point-count">
          Showing {filteredPoints.length} of {points.length} registered storage points.
        </p>
      )}
    </section>
  );
}

export function StoragePointFormPage() {
  const { pointId } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(pointId);
  const [form, setForm] = useState(EMPTY_STORAGE_POINT);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [locationMessage, setLocationMessage] = useState("");

  useEffect(() => {
    if (!editing) return;
    getStoragePoint(pointId)
      .then((point) => setForm({
        name: point.name,
        point_code: point.point_code,
        address: point.address ?? "",
        latitude: point.latitude,
        longitude: point.longitude,
        waste_quantity_kg: point.waste_quantity_kg,
        availability_status: point.availability_status,
        available_from: point.available_from?.slice(0, 16) ?? "",
        description: point.description ?? "",
      }))
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [editing, pointId]);

  function setField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
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
      point_code: form.point_code.trim().toUpperCase(),
      address: form.address.trim(),
      latitude: Number(form.latitude),
      longitude: Number(form.longitude),
      waste_quantity_kg: Number(form.waste_quantity_kg),
      available_from: form.available_from || null,
      description: form.description.trim(),
    };
    try {
      const point = editing
        ? await updateStoragePoint(pointId, payload)
        : await createStoragePoint(payload);
      navigate(`/storage-points/${point.id}`, { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setSaving(false);
    }
  }

  if (loading) return <p className="scenario-status">Loading storage point…</p>;

  return (
    <section className="storage-point-page">
      <StoragePointHeading
        title={editing ? "Edit storage point" : "Add storage point"}
        subtitle="Use verified location coordinates and the actual recorded waste quantity."
      />
      <StoragePointError message={error} />
      <form className="scenario-form panel storage-point-form" onSubmit={submit}>
        <label className="scenario-field">
          <span>Storage point name</span>
          <input name="name" value={form.name} onChange={setField} maxLength="150" required />
        </label>
        <label className="scenario-field">
          <span>Point code</span>
          <input name="point_code" value={form.point_code} onChange={setField} maxLength="50" required />
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
        <label className="scenario-field">
          <span>Waste quantity (kg)</span>
          <input name="waste_quantity_kg" type="number" step="0.01" min="0" value={form.waste_quantity_kg} onChange={setField} required />
        </label>
        <label className="scenario-field">
          <span>Availability</span>
          <select name="availability_status" value={form.availability_status} onChange={setField}>
            <option value="available">Available</option>
            <option value="unavailable">Unavailable</option>
          </select>
        </label>
        <label className="scenario-field">
          <span>Waste available from</span>
          <input name="available_from" type="datetime-local" value={form.available_from} onChange={setField} />
        </label>
        <label className="scenario-field">
          <span>Description</span>
          <textarea name="description" value={form.description} onChange={setField} rows="3" maxLength="5000" />
        </label>
        <p className="storage-point-form-note">
          Times are Indian Standard Time. A vehicle that arrives early waits until the waste is available.
        </p>
        <div className="scenario-form-actions">
          <Link className="secondary-action" to={editing ? `/storage-points/${pointId}` : "/storage-points"}>Cancel</Link>
          <button className="primary-action" type="submit" disabled={saving}>
            {saving ? "Saving…" : editing ? "Save changes" : "Add storage point"}
          </button>
        </div>
      </form>
    </section>
  );
}

export function StoragePointDetailPage() {
  const { pointId } = useParams();
  const navigate = useNavigate();
  const [point, setPoint] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getStoragePoint(pointId)
      .then(setPoint)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [pointId]);

  async function removePoint() {
    if (!window.confirm(`Delete "${point.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    setError("");
    try {
      await deleteStoragePoint(point.id);
      navigate("/storage-points", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setDeleting(false);
    }
  }

  if (loading) return <p className="scenario-status">Loading storage point…</p>;
  if (!point) {
    return (
      <section className="storage-point-page">
        <StoragePointError message={error || "Storage point not found."} />
        <Link className="panel-link" to="/storage-points">← All storage points</Link>
      </section>
    );
  }

  return (
    <section className="storage-point-page">
      <StoragePointHeading
        title={point.name}
        subtitle={point.point_code}
        action={
          <div className="scenario-actions">
            <Link className="secondary-action" to={`/storage-points/${point.id}/edit`}>Edit point</Link>
            <button type="button" className="danger-action" onClick={removePoint} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </button>
          </div>
        }
      />
      <StoragePointError message={error} />
      <article className="panel storage-point-details">
        <div className="panel-head">
          <h2>Storage point details</h2>
          <span className={`pill ${point.availability_status === "available" ? "pill-ok" : "pill-off"}`}>
            {point.availability_status}
          </span>
        </div>
        <dl className="scenario-detail-list">
          <div><dt>Point code</dt><dd>{point.point_code}</dd></div>
          <div><dt>Address</dt><dd>{point.address || "Not provided"}</dd></div>
          <div><dt>Latitude</dt><dd>{point.latitude}</dd></div>
          <div><dt>Longitude</dt><dd>{point.longitude}</dd></div>
          <div><dt>Waste quantity</dt><dd>{Number(point.waste_quantity_kg).toLocaleString()} kg</dd></div>
          <div><dt>Description</dt><dd>{point.description || "Not provided"}</dd></div>
          <div><dt>Created</dt><dd>{new Date(point.created_at).toLocaleDateString()}</dd></div>
          <div><dt>Last updated</dt><dd>{new Date(point.updated_at).toLocaleDateString()}</dd></div>
        </dl>
      </article>
      <StoragePointMap points={[point]} />
      <Link className="panel-link scenario-back-link" to="/storage-points">← All storage points</Link>
    </section>
  );
}
