import { useEffect, useState } from "react";
import { ROLE_LABELS } from "../auth/permissions.js";
import {
  createTeamMember,
  deleteTeamMember,
  getTeam,
  updateTeamMemberRole,
} from "../services/api.js";
import { PageError, PageHeading } from "./ScenarioManagementPage.jsx";

const TEAM_ROLES = ["reviewer", "management", "driver", "facility"];
const EMPTY_FORM = { name: "", email: "", role: "reviewer", password: "" };

function RoleOptions() {
  return TEAM_ROLES.map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>);
}

export default function TeamPage() {
  const [members, setMembers] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getTeam().then(setMembers).catch((failure) => setError(failure.message));
  }, []);

  async function act(action) {
    setError("");
    setSaving(true);
    try {
      await action();
      setMembers(await getTeam());
    } catch (failure) {
      setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  function setField(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  function addAccount(event) {
    event.preventDefault();
    act(async () => {
      await createTeamMember(form);
      setForm(EMPTY_FORM);
    });
  }

  function removeAccount(member) {
    if (!window.confirm(`Remove ${member.name}'s account? This cannot be undone.`)) return;
    act(() => deleteTeamMember(member.id));
  }

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="TEAM"
        title="Team"
        subtitle="Accounts that read this workspace. These roles are proposed views, and their real authority is not confirmed."
      />
      <PageError message={error} />

      <section className="panel report-scroll">
        <table className="report-table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.id}>
                <td>{member.name}</td>
                <td>{member.email}</td>
                <td>
                  <select
                    aria-label={`Role for ${member.name}`}
                    value={member.role}
                    disabled={saving}
                    onChange={(event) => act(() => updateTeamMemberRole(member.id, event.target.value))}
                  >
                    <RoleOptions />
                  </select>
                </td>
                <td>
                  <button
                    type="button"
                    className="danger-action"
                    aria-label={`Remove ${member.name}`}
                    disabled={saving}
                    onClick={() => removeAccount(member)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!members.length && <p className="panel-note">No team accounts yet.</p>}
      </section>

      <form className="panel scenario-form" onSubmit={addAccount}>
        <div className="panel-head"><h2>Add an account</h2></div>
        <label className="scenario-field">
          <span>Name</span>
          <input name="name" value={form.name} onChange={setField} maxLength="100" required />
        </label>
        <label className="scenario-field">
          <span>Email</span>
          <input name="email" type="email" value={form.email} onChange={setField} required />
        </label>
        <label className="scenario-field">
          <span>Role</span>
          <select name="role" value={form.role} onChange={setField}>
            <RoleOptions />
          </select>
        </label>
        <label className="scenario-field">
          <span>Temporary password</span>
          <input
            name="password"
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={setField}
            minLength="8"
            maxLength="128"
            required
          />
        </label>
        <div className="scenario-form-actions">
          <button className="primary-action" type="submit" disabled={saving}>Add account</button>
        </div>
      </form>
    </section>
  );
}
