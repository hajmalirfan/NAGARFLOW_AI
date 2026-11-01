const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const AUTH = "/api/v1/auth";

async function request(path, options = {}) {
  let response;
  const token = localStorage.getItem("nagarflow_token");
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error(
      `Unable to reach the NagarFlow API at ${API_BASE_URL}. Start FastAPI from the backend folder and try again.`,
    );
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(describeFailure(response, data, path));
    error.status = response.status;
    error.report = data.detail?.report;
    throw error;
  }
  return data;
}

function describeFailure(response, data, path) {
  // A 404 on one of our own endpoints almost never means "no such record":
  // it means the API process does not serve this route. The usual cause is
  // a FastAPI server started before the route existed and left running
  // without --reload. Say so, because a bare "Not Found" reads like a
  // generic outage and gets mistaken for a database problem.
  if (response.status === 404) {
    return (
      `The API at ${API_BASE_URL} does not have this endpoint (${path}). ` +
      "It is most likely running an older version of the backend. Restart " +
      "FastAPI from the backend folder and try again."
    );
  }
  if (typeof data.detail === "string") {
    return data.reference ? `${data.detail} Reference: ${data.reference}.` : data.detail;
  }
  if (Array.isArray(data.detail)) {
    return data.detail.map((issue) => issue.msg).join(" ");
  }
  if (typeof data.detail?.message === "string") {
    return data.detail.message;
  }
  if (response.status >= 500) {
    return (
      `The NagarFlow API returned a server error (${response.status}). ` +
      "Check the backend terminal for the full traceback."
    );
  }
  return "Something went wrong. Please try again.";
}

export async function getApiHealth() {
  return request("/health");
}

export async function register(credentials) {
  return request(`${AUTH}/register`, {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export async function login(credentials) {
  return request(`${AUTH}/login`, {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export async function getCurrentUser() {
  return request(`${AUTH}/me`);
}

export async function forgotPassword(email) {
  return request(`${AUTH}/forgot-password`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function verifyResetToken(token) {
  return request(`${AUTH}/verify-reset-token`, {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function resetPassword(token, password) {
  return request(`${AUTH}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
}

export async function getDashboardSummary() {
  return request("/api/v1/dashboard/summary");
}

export async function getScenarioOptions() {
  return request("/api/v1/scenarios/options");
}

export async function getScenarios() {
  return request("/api/v1/scenarios");
}

export async function getScenario(id) {
  return request(`/api/v1/scenarios/${id}`);
}

export async function createScenario(scenario) {
  return request("/api/v1/scenarios", {
    method: "POST",
    body: JSON.stringify(scenario),
  });
}

export async function updateScenario(id, scenario) {
  return request(`/api/v1/scenarios/${id}`, {
    method: "PUT",
    body: JSON.stringify(scenario),
  });
}

export async function deleteScenario(id) {
  return request(`/api/v1/scenarios/${id}`, { method: "DELETE" });
}

export async function getDepots() {
  return request("/api/v1/depots");
}

export async function getDepot(id) {
  return request(`/api/v1/depots/${id}`);
}

export async function createDepot(depot) {
  return request("/api/v1/depots", {
    method: "POST",
    body: JSON.stringify(depot),
  });
}

export async function updateDepot(id, depot) {
  return request(`/api/v1/depots/${id}`, {
    method: "PUT",
    body: JSON.stringify(depot),
  });
}

export async function deleteDepot(id) {
  return request(`/api/v1/depots/${id}`, { method: "DELETE" });
}

export async function getVehicles() {
  return request("/api/v1/vehicles");
}

export async function getVehicle(id) {
  return request(`/api/v1/vehicles/${id}`);
}

export async function createVehicle(vehicle) {
  return request("/api/v1/vehicles", {
    method: "POST",
    body: JSON.stringify(vehicle),
  });
}

export async function updateVehicle(id, vehicle) {
  return request(`/api/v1/vehicles/${id}`, {
    method: "PUT",
    body: JSON.stringify(vehicle),
  });
}

export async function deleteVehicle(id) {
  return request(`/api/v1/vehicles/${id}`, { method: "DELETE" });
}

export async function getStoragePoints() {
  return request("/api/v1/storage-points");
}

export async function getStoragePoint(id) {
  return request(`/api/v1/storage-points/${id}`);
}

export async function createStoragePoint(point) {
  return request("/api/v1/storage-points", {
    method: "POST",
    body: JSON.stringify(point),
  });
}

export async function updateStoragePoint(id, point) {
  return request(`/api/v1/storage-points/${id}`, {
    method: "PUT",
    body: JSON.stringify(point),
  });
}

export async function deleteStoragePoint(id) {
  return request(`/api/v1/storage-points/${id}`, { method: "DELETE" });
}

export async function getFacilities() {
  return request("/api/v1/facilities");
}

export async function getFacility(id) {
  return request(`/api/v1/facilities/${id}`);
}

export async function getFacilityCapacity(id) {
  return request(`/api/v1/facilities/${id}/capacity`);
}

export async function createFacility(facility) {
  return request("/api/v1/facilities", {
    method: "POST",
    body: JSON.stringify(facility),
  });
}

export async function updateFacility(id, facility) {
  return request(`/api/v1/facilities/${id}`, {
    method: "PUT",
    body: JSON.stringify(facility),
  });
}

export async function deleteFacility(id) {
  return request(`/api/v1/facilities/${id}`, { method: "DELETE" });
}

export async function validateScenario(id) {
  return request(`/api/v1/scenarios/${id}/validate`, { method: "POST" });
}

export async function optimizeScenario(id) {
  return request(`/api/v1/scenarios/${id}/optimize`, { method: "POST" });
}

export async function getLatestOptimization(id) {
  return request(`/api/v1/scenarios/${id}/optimization`);
}

export async function getOptimizationBatch(id, batchId) {
  return request(`/api/v1/scenarios/${id}/optimization/${batchId}`);
}

export async function getOptimizationHistory(filters) {
  const query = new URLSearchParams(
    Object.entries(filters).filter(([, value]) => value !== ""),
  );
  return request(`/api/v1/optimization-history?${query}`);
}

export async function getScenarioValidations(id) {
  return request(`/api/v1/scenarios/${id}/validations`);
}
