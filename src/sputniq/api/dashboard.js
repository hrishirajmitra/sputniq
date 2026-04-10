const state = {
  deployments: [],
  workflows: [],
  tools: [],
  chatSessions: {},
  selectedServiceId: "",
};

function el(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setMessage(kind, message) {
  const box = el("uploadMessage");
  box.className = `message-box ${kind}`;
  box.textContent = message;
}

function clearMessage() {
  const box = el("uploadMessage");
  box.className = "message-box";
  box.textContent = "";
}

function updateRefreshTime() {
  el("refreshTime").textContent = new Date().toLocaleTimeString();
}

function serviceUrl(deployment, path = "") {
  if (!deployment.port) {
    return "";
  }

  return `http://${window.location.hostname}:${deployment.port}${path}`;
}

function selectedDeployment() {
  return state.deployments.find((deployment) => deployment.service_id === state.selectedServiceId) || null;
}

function ensureSession(serviceId) {
  if (!state.chatSessions[serviceId]) {
    state.chatSessions[serviceId] = [];
  }
  return state.chatSessions[serviceId];
}

function appendMessage(serviceId, message) {
  ensureSession(serviceId).push(message);
  renderTranscript();
}

function renderDeployments() {
  const tbody = el("deploymentTable").querySelector("tbody");
  const deployments = state.deployments;
  el("deploymentCount").textContent = deployments.length;
  el("deploymentBadge").textContent = `${deployments.length} service${deployments.length === 1 ? "" : "s"}`;

  if (!deployments.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state">No managed services have been deployed yet.</div></td></tr>`;
    return;
  }

  tbody.innerHTML = deployments.map((deployment) => {
    const status = deployment.status || "unknown";
    const selectButton = deployment.chat_ready
      ? `<button type="button" data-chat-target="${deployment.service_id}" class="ghost">Use in Chat</button>`
      : `<span class="label">No chat</span>`;

    return `
      <tr>
        <td>
          <strong>${escapeHtml(deployment.service_id)}</strong><br>
          <code>${escapeHtml(deployment.image || "unknown")}</code>
        </td>
        <td><span class="status-pill ${status}"><span class="status-dot"></span>${escapeHtml(status)}</span></td>
        <td>${escapeHtml(deployment.service_kind || "-")}</td>
        <td>${escapeHtml(deployment.app_name || "-")}</td>
        <td>${deployment.port ? `<code>${deployment.port}</code>` : "-"}</td>
        <td>${selectButton}</td>
        <td><code>${escapeHtml(deployment.logs_cmd)}</code></td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("[data-chat-target]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedServiceId = button.getAttribute("data-chat-target");
      renderChatTargets();
      renderTranscript();
    });
  });
}

function renderWorkflows() {
  const tbody = el("workflowTable").querySelector("tbody");
  el("workflowCount").textContent = state.workflows.length;

  if (!state.workflows.length) {
    tbody.innerHTML = `<tr><td colspan="3"><div class="empty-state">No workflows registered yet.</div></td></tr>`;
    return;
  }

  tbody.innerHTML = state.workflows.map((workflow) => `
    <tr>
      <td><strong>${escapeHtml(workflow.id)}</strong></td>
      <td>${escapeHtml(workflow.description || "-")}</td>
      <td>${escapeHtml(workflow.entrypoint_step)}</td>
    </tr>
  `).join("");
}

function renderTools() {
  const tbody = el("toolTable").querySelector("tbody");
  el("toolCount").textContent = state.tools.length;

  if (!state.tools.length) {
    tbody.innerHTML = `<tr><td colspan="3"><div class="empty-state">No tools registered yet.</div></td></tr>`;
    return;
  }

  tbody.innerHTML = state.tools.map((tool) => `
    <tr>
      <td><strong>${escapeHtml(tool.id)}</strong></td>
      <td><code>${escapeHtml(tool.entrypoint)}</code></td>
      <td>${tool.timeout_ms || 10000} ms</td>
    </tr>
  `).join("");
}

function renderChatTargets() {
  const select = el("chatTarget");
  const targets = state.deployments.filter((deployment) => deployment.chat_ready && deployment.status === "running");
  el("chatTargetCount").textContent = targets.length;

  if (!targets.length) {
    select.innerHTML = `<option value="">No running agent services</option>`;
    state.selectedServiceId = "";
    el("chatStatusBadge").textContent = "No target";
    el("chatMeta").textContent = "Deploy an agent bundle to unlock the in-platform chatbox.";
    el("chatUrlLabel").textContent = "";
    return;
  }

  if (!targets.some((deployment) => deployment.service_id === state.selectedServiceId)) {
    state.selectedServiceId = targets[0].service_id;
  }

  select.innerHTML = targets.map((deployment) => `
    <option value="${deployment.service_id}">${deployment.service_id} | ${deployment.app_name || "app"} | port ${deployment.port}</option>
  `).join("");
  select.value = state.selectedServiceId;

  const deployment = selectedDeployment();
  if (!deployment) {
    return;
  }

  el("chatStatusBadge").textContent = `${deployment.service_id} ready`;
  el("chatMeta").textContent = `${deployment.app_name} | ${deployment.image}`;
  el("chatUrlLabel").textContent = serviceUrl(deployment, deployment.chat_path || "");
}

function renderTranscript() {
  const container = el("transcript");
  const deployment = selectedDeployment();

  if (!deployment) {
    container.innerHTML = `<div class="empty-state">Pick a running agent target to start a transcript.</div>`;
    return;
  }

  const messages = ensureSession(deployment.service_id);
  if (!messages.length) {
    container.innerHTML = `<div class="empty-state">The transcript for <strong>${escapeHtml(deployment.service_id)}</strong> is empty. Send a message to verify the deployed agent.</div>`;
    return;
  }

  container.innerHTML = messages.map((message) => {
    const eventMarkup = Array.isArray(message.events) && message.events.length
      ? `
        <div class="event-list">
          ${message.events.map((event) => `
            <div class="event-item">
              <strong>${escapeHtml(event.type)}</strong><br>
              <code>${escapeHtml(JSON.stringify(event.payload))}</code>
            </div>
          `).join("")}
        </div>
      `
      : "";

    return `
      <div class="bubble ${message.role}">
        ${escapeHtml(message.content)}
        ${eventMarkup}
      </div>
    `;
  }).join("");

  container.scrollTop = container.scrollHeight;
}

async function fetchData() {
  try {
    const [workflowResponse, toolResponse, deploymentResponse] = await Promise.all([
      fetch("/api/v1/registry/workflows"),
      fetch("/api/v1/registry/tools"),
      fetch("/api/v1/registry/deployments"),
    ]);

    const workflowData = await workflowResponse.json();
    const toolData = await toolResponse.json();
    const deploymentData = await deploymentResponse.json();

    state.workflows = Array.isArray(workflowData) ? workflowData : [];
    state.tools = Array.isArray(toolData) ? toolData : [];
    state.deployments = Array.isArray(deploymentData) ? deploymentData : [];

    renderDeployments();
    renderWorkflows();
    renderTools();
    renderChatTargets();
    renderTranscript();
    updateRefreshTime();
  } catch (error) {
    console.error("Failed to refresh dashboard state", error);
  }
}

async function deployZip(event) {
  event.preventDefault();
  clearMessage();

  const file = el("zipFile").files[0];
  if (!file) {
    setMessage("error", "Choose a ZIP archive before deploying.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  const button = el("deployButton");
  button.disabled = true;
  button.textContent = "Deploying...";

  try {
    const response = await fetch("/api/v1/registry/upload-zip", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Deployment failed");
    }

    setMessage("success", data.message);
    await fetchData();
  } catch (error) {
    setMessage("error", error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Upload and Deploy";
  }
}

async function sendChat(event) {
  event.preventDefault();

  const deployment = selectedDeployment();
  if (!deployment) {
    appendMessage("unassigned", {
      role: "system",
      content: "No chat-capable deployment is selected yet.",
    });
    return;
  }

  const input = el("chatInput");
  const message = input.value.trim();
  if (!message) {
    return;
  }

  const history = ensureSession(deployment.service_id)
    .filter((item) => item.role === "user" || item.role === "assistant")
    .map((item) => ({ role: item.role, content: item.content }));

  appendMessage(deployment.service_id, { role: "user", content: message });
  input.value = "";

  const button = el("sendChat");
  button.disabled = true;
  button.textContent = "Waiting...";

  try {
    const response = await fetch(serviceUrl(deployment, deployment.chat_path || "/api/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history,
        context: {
          workflow_ids: deployment.workflow_ids || [],
          app_name: deployment.app_name,
        },
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Chat request failed");
    }

    appendMessage(deployment.service_id, {
      role: "assistant",
      content: data.reply,
      events: data.events || [],
    });
  } catch (error) {
    appendMessage(deployment.service_id, {
      role: "system",
      content: `Chat request failed: ${error.message}`,
    });
  } finally {
    button.disabled = false;
    button.textContent = "Send Message";
  }
}

function clearChat() {
  const deployment = selectedDeployment();
  if (!deployment) {
    return;
  }

  state.chatSessions[deployment.service_id] = [];
  renderTranscript();
}

function initialize() {
  el("uploadForm").addEventListener("submit", deployZip);
  el("chatForm").addEventListener("submit", sendChat);
  el("clearChat").addEventListener("click", clearChat);
  el("refreshNow").addEventListener("click", fetchData);
  el("chatTarget").addEventListener("change", (event) => {
    state.selectedServiceId = event.target.value;
    renderChatTargets();
    renderTranscript();
  });

  fetchData();
  window.setInterval(fetchData, 5000);
}

document.addEventListener("DOMContentLoaded", initialize);
