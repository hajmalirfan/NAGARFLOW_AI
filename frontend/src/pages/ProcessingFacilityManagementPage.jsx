import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import FacilityMap from "../components/FacilityMap.jsx";
import {
  createFacility,
  deleteFacility,
  getFacilities,
  getFacility,
  getFacilityCapacity,
  updateFacility,
} from "../services/api.js";

const integer = new Intl.NumberFormat("en-IN");
const decimal = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

function formatKg(value) {
  return `${decimal.format(Number(value))} kg`;
}

function FacilityError({ message }) {
  return message ? <p className="form-error facility-error" role="alert">{message}</p> : null;
}

function FacilityHeading({ title, subtitle, action }) {
  return (
    <div className="page-head">
      <div>
        <p className="page-kicker">PROCESSING FACILITY</p>
        <h1>{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

const EMPTY_FACILITY = {
  name: "",
  facility_code: "",
  address: "",
  latitude: "",
  longitude: "",
  total_capacity_kg: "",
  status: "active",
  description: "",
};

/** The shared capacity pool, shown as a bar plus the three figures. */
function CapacityMonitor({ capacity }) {
  if (!capacity) return null;
  const total = Number(capacity.total_capacity_kg);
  const allocated = Number(capacity.allocated_kg);
  const used = total > 0 ? Math.min(Math.max(allocated / total, 0), 1) : 0;

  return (
    <section className="panel capacity-monitor">
      <div className="panel-head">
        <div>
          <h2>Shared capacity</h2>
          <p>
            One pool across both vehicle deliveries, not a per-vehicle allowance.
          </p>
        </div>
        <span className={`pill ${capacity.is_within_capacity ? "pill-ok" : "pill-off"}`}>
          {capacity.is_within_capacity ? "Within capacity" : "Over capacity"}
        </span>
      </div>
      <div
        className="capacity-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={allocated}
        aria-label="Allocated share of facility capacity"
      >
        <span
          className={`capacity-bar-fill${capacity.is_within_capacity ? "" : " capacity-bar-over"}`}
          style={{ width: `${used * 100}%` }}
        />
      </div>
      <div className="split-stat">
        <div><strong>{formatKg(capacity.total_capacity_kg)}</strong><span>Total capacity</span></div>
        <div><strong>{formatKg(capacity.allocated_kg)}</strong><span>Committed by scenarios</span></div>
        <div><strong>{formatKg(capacity.remaining_capacity_kg)}</strong><span>Remaining capacity</span></div>
      </div>
      {capacity.scenarios.length === 0 ? (
        <p className="panel-note">
          No scenario delivers here yet, so the whole capacity is available.
        </p>
      ) : (
        <ul className="row-list">
          {capacity.scenarios.map((scenario) => (
            <li key={scenario.id}>
              <span className="row-main">
                {scenario.name}
                <small>{scenario.reference}</small>
              </span>
              <span className="row-value">{formatKg(scenario.allocated_kg)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function FacilityListPage() {
  const [facilities, setFacilities] = useState([]);
  const [capacityById, setCapacityById] = useState({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");

  useEffect(() => {
    let active = true;
    getFacilities()
      .then(async (records) => {
        if (!active) return;
        setFacilities(records);
        // Capacity is a separate endpoint per facility, so fetch each one
        // and ignore any that fail rather than losing the whole list.
        const entries = await Promise.all(
          records.map(async (facility) => {
            try {
              return [facility.id, await getFacilityCapacity(facility.id)];
            } catch {
              return [facility.id, null];
            }
          }),
        );
        if (!active) return;
        setCapacityById(Object.fromEntries(entries.filter(([, value]) => value)));
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return facilities.filter((facility) => {
      const matchesStatus = status === "all" || facility.status === status;
      if (!term) return matchesStatus;
      const haystack = [facility.name, facility.facility_code, facility.address ?? ""]
        .join(" ")
        .toLowerCase();
      return matchesStatus && haystack.includes(term);
    });
  }, [facilities, search, status]);

  if (loading) {
    return (
      <div className="page-loading">
        <span className="loading-dot" />
        <p>Loading processing facilities…</p>
      </div>
    );
  }

  return (
    <div className="facility-page">
      <FacilityHeading
        title="Processing Facility Management"
        subtitle="Where both collection vehicles deliver their waste. Capacity is one shared limit."
        action={
          <Link className="primary-action" to="/facility/new">
            Add facility<span aria-hidden="true">→</span>
          </Link>
        }
      />
      <FacilityError message={error} />

      <div className="storage-point-filters">
        <label>
          <span>Search facilities</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name, code, or address"
          />
        </label>
        <label>
          <span>Status</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
      </div>

      {facilities.length === 0 ? (
        <div className="notice">
          <strong>No facility configured yet.</strong> A scenario needs one processing
          facility with a valid location and a capacity greater than zero.
        </div>
      ) : (
        <section className="panel">
          <div className="panel-head">
            <h2>Registered facilities</h2>
            <span className="row-meta">{integer.format(visible.length)} shown</span>
          </div>
          {visible.length === 0 ? (
            <p className="storage-map-empty">No facility matches this search.</p>
          ) : (
            <ul className="row-list">
              {visible.map((facility) => {
                const capacity = capacityById[facility.id];
                return (
                  <li key={facility.id}>
                    <span className="row-main">
                      <Link className="scenario-row-link" to={`/facility/${facility.id}`}>
                        {facility.name}
                      </Link>
                      <small>{facility.facility_code}</small>
                    </span>
                    <span className="row-meta">
                      {facility.latitude}, {facility.longitude}
                    </span>
                    <span className="row-value">{formatKg(facility.total_capacity_kg)}</span>
                    <span className="row-meta">
                      {capacity
                        ? `${formatKg(capacity.remaining_capacity_kg)} left`
                        : "capacity pending"}
                    </span>
                    <span className={`pill ${facility.status === "active" ? "pill-ok" : "pill-off"}`}>
                      {facility.status}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      <FacilityMap facilities={visible} capacityById={capacityById} />
    </div>
  );
}

export function FacilityFormPage() {
  const { facilityId } = useParams();
  const editing = Boolean(facilityId);
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY_FACILITY);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!editing) return undefined;
    let active = true;
    getFacility(facilityId)
      .then((facility) => {
        if (!active) return;
        setForm({
          name: facility.name,
          facility_code: facility.facility_code,
          address: facility.address ?? "",
          latitude: String(facility.latitude),
          longitude: String(facility.longitude),
          total_capacity_kg: String(facility.total_capacity_kg),
          status: facility.status,
          description: facility.description ?? "",
        });
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [editing, facilityId]);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    const capacity = Number(form.total_capacity_kg);
    if (!Number.isFinite(capacity) || capacity <= 0) {
      setError("Total capacity must be greater than zero.");
      return;
    }
    const latitude = Number(form.latitude);
    const longitude = Number(form.longitude);
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
      setError("Latitude must be between -90 and 90.");
      return;
    }
    if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
      setError("Longitude must be between -180 and 180.");
      return;
    }

    const payload = {
      name: form.name.trim(),
      facility_code: form.facility_code.trim(),
      address: form.address.trim(),
      latitude,
      longitude,
      total_capacity_kg: capacity,
      status: form.status,
      description: form.description.trim(),
    };

    setSaving(true);
    try {
      const saved = editing
        ? await updateFacility(facilityId, payload)
        : await createFacility(payload);
      navigate(`/facility/${saved.id}`, { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="page-loading">
        <span className="loading-dot" />
        <p>Loading facility…</p>
      </div>
    );
  }

  return (
    <div className="facility-page">
      <FacilityHeading
        title={editing ? "Edit processing facility" : "Add processing facility"}
        subtitle="Capacity must be greater than zero and is shared across both vehicle deliveries."
      />
      <form className="panel facility-form" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="name">Facility name</label>
          <div className="input-wrap">
            <input
              id="name"
              value={form.name}
              onChange={(event) => update("name", event.target.value)}
              placeholder="Central Waste Processing Plant"
              required
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="facility_code">Facility code</label>
          <div className="input-wrap">
            <input
              id="facility_code"
              value={form.facility_code}
              onChange={(event) => update("facility_code", event.target.value)}
              placeholder="FAC001"
              required
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="address">Address</label>
          <div className="input-wrap">
            <input
              id="address"
              value={form.address}
              onChange={(event) => update("address", event.target.value)}
              placeholder="Trichy Industrial Area"
            />
          </div>
        </div>
        <div className="facility-form-row">
          <div className="field">
            <label htmlFor="latitude">Latitude</label>
            <div className="input-wrap">
              <input
                id="latitude"
                value={form.latitude}
                onChange={(event) => update("latitude", event.target.value)}
                placeholder="10.8150"
                required
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="longitude">Longitude</label>
            <div className="input-wrap">
              <input
                id="longitude"
                value={form.longitude}
                onChange={(event) => update("longitude", event.target.value)}
                placeholder="78.6850"
                required
              />
            </div>
          </div>
        </div>
        <div className="facility-form-row">
          <div className="field">
            <label htmlFor="total_capacity_kg">Total capacity (kg)</label>
            <div className="input-wrap">
              <input
                id="total_capacity_kg"
                value={form.total_capacity_kg}
                onChange={(event) => update("total_capacity_kg", event.target.value)}
                placeholder="10000"
                required
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="status">Status</label>
            <div className="input-wrap">
              <select
                id="status"
                value={form.status}
                onChange={(event) => update("status", event.target.value)}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>
        </div>
        <div className="field">
          <label htmlFor="description">Description</label>
          <div className="input-wrap">
            <textarea
              id="description"
              rows={3}
              value={form.description}
              onChange={(event) => update("description", event.target.value)}
              placeholder="Additional details about this facility"
            />
          </div>
        </div>
        <FacilityError message={error} />
        <div className="facility-form-actions">
          <button className="submit-button" type="submit" disabled={saving}>
            {saving ? "Saving…" : editing ? "Save facility" : "Create facility"}
          </button>
          <Link className="panel-link" to="/facility">Cancel</Link>
        </div>
      </form>
    </div>
  );
}

export function FacilityDetailPage() {
  const { facilityId } = useParams();
  const navigate = useNavigate();
  const [facility, setFacility] = useState(null);
  const [capacity, setCapacity] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([getFacility(facilityId), getFacilityCapacity(facilityId).catch(() => null)])
      .then(([record, capacityRecord]) => {
        if (!active) return;
        setFacility(record);
        setCapacity(capacityRecord);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [facilityId]);

  async function toggleStatus() {
    setError("");
    setBusy(true);
    try {
      const next = facility.status === "active" ? "inactive" : "active";
      const saved = await updateFacility(facilityId, {
        name: facility.name,
        facility_code: facility.facility_code,
        address: facility.address ?? "",
        latitude: facility.latitude,
        longitude: facility.longitude,
        total_capacity_kg: facility.total_capacity_kg,
        status: next,
        description: facility.description ?? "",
      });
      setFacility(saved);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    setError("");
    setBusy(true);
    try {
      await deleteFacility(facilityId);
      navigate("/facility", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="page-loading">
        <span className="loading-dot" />
        <p>Loading facility…</p>
      </div>
    );
  }

  if (!facility) {
    return (
      <div className="facility-page">
        <FacilityHeading title="Processing facility" subtitle="This facility could not be loaded." />
        <FacilityError message={error} />
        <Link className="panel-link" to="/facility">← Back to facilities</Link>
      </div>
    );
  }

  return (
    <div className="facility-page">
      <FacilityHeading
        title={facility.name}
        subtitle={`${facility.facility_code} · ${facility.address || "Address not recorded"}`}
        action={
          <div className="facility-detail-actions">
            <Link className="primary-action" to={`/facility/${facility.id}/edit`}>
              Edit facility
            </Link>
            <button type="button" className="signout-button" onClick={toggleStatus} disabled={busy}>
              {facility.status === "active" ? "Deactivate" : "Activate"}
            </button>
            <button type="button" className="signout-button" onClick={handleDelete} disabled={busy}>
              Delete
            </button>
          </div>
        }
      />
      <FacilityError message={error} />

      <section className="panel">
        <div className="panel-head"><h2>Facility details</h2></div>
        <dl className="detail-list">
          <div><dt>Facility code</dt><dd>{facility.facility_code}</dd></div>
          <div><dt>Address</dt><dd>{facility.address || "Not recorded"}</dd></div>
          <div><dt>Latitude</dt><dd>{facility.latitude}</dd></div>
          <div><dt>Longitude</dt><dd>{facility.longitude}</dd></div>
          <div><dt>Total capacity</dt><dd>{formatKg(facility.total_capacity_kg)}</dd></div>
          <div><dt>Status</dt><dd>{facility.status}</dd></div>
          <div><dt>Description</dt><dd>{facility.description || "Not recorded"}</dd></div>
        </dl>
      </section>

      <CapacityMonitor capacity={capacity} />

      <FacilityMap
        facilities={[facility]}
        capacityById={capacity ? { [facility.id]: capacity } : {}}
      />

      <Link className="panel-link" to="/facility">← Back to facilities</Link>
    </div>
  );
}
