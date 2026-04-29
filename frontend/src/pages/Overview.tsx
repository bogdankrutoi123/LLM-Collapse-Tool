import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { Model, Prompt, Notification } from "../api/types";

export default function Overview() {
  const [models, setModels] = useState<Model[]>([]);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<Model[]>("/api/v1/models/"),
      apiFetch<Prompt[]>("/api/v1/prompts/?limit=10"),
      apiFetch<Notification[]>("/api/v1/notifications/").catch(() => [])
    ])
      .then(([modelsData, promptsData, notifData]) => {
        setModels(modelsData);
        setPrompts(promptsData);
        setNotifications(notifData);
      })
      .catch((err) => setError(err.message));
  }, []);

  const pendingAlerts = notifications.filter((n) => n.status === "pending");

  return (
    <div className="grid">
      <div className="grid grid-3">
        <div className="card stat-card">
          <div className="small">Models Registered</div>
          <strong className="stat-value">{models.length}</strong>
        </div>
        <div className="card stat-card">
          <div className="small">Total Prompts</div>
          <strong className="stat-value">{prompts.length > 0 ? `${prompts.length}+` : "0"}</strong>
        </div>
        <div className="card stat-card">
          <div className="small">Pending Alerts</div>
          <strong className="stat-value" style={pendingAlerts.length > 0 ? {color: "#ef4444"} : {}}>
            {pendingAlerts.length}
          </strong>
        </div>
      </div>

      {error && <p className="small">{error}</p>}

      <div className="card">
        <h2>Getting Started</h2>
        <div className="steps">
          <div className="step">
            <span className="step-num">1</span>
            <div>
              <strong>Register a Model</strong>
              <p className="small">Go to <strong>Models</strong> and create a model entry. Then add a version with a HuggingFace model ID (e.g. <code>microsoft/phi-1_5</code>).</p>
            </div>
          </div>
          <div className="step">
            <span className="step-num">2</span>
            <div>
              <strong>Run a Benchmark</strong>
              <p className="small">Go to <strong>Benchmark</strong>, select your model version, choose a dataset (WikiText-2 is default), and run the benchmark to compute distribution metrics.</p>
            </div>
          </div>
          <div className="step">
            <span className="step-num">3</span>
            <div>
              <strong>Compare Versions</strong>
              <p className="small">After benchmarking multiple versions, go to <strong>Analysis</strong> to compare metrics side-by-side and track entropy/divergence trends.</p>
            </div>
          </div>
          <div className="step">
            <span className="step-num">4</span>
            <div>
              <strong>Set Up Alerts</strong>
              <p className="small">Configure <strong>Alert Rules</strong> with thresholds on metrics like JS divergence or entropy. The system will create notifications and collapse events automatically.</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="topbar">
            <h3>Models</h3>
            <span className="badge">{models.length}</span>
          </div>
          {models.length === 0 && <p className="small">No models registered yet.</p>}
          <table className="table">
            <tbody>
              {models.map((model) => (
                <tr key={model.id}>
                  <td><strong>{model.name}</strong></td>
                  <td><span className="badge">{model.status}</span></td>
                  <td className="small">{model.source || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="topbar">
            <h3>Recent Prompts</h3>
            <span className="badge">{prompts.length}</span>
          </div>
          {prompts.length === 0 && <p className="small">No prompts submitted yet.</p>}
          <table className="table">
            <tbody>
              {prompts.slice(0, 8).map((prompt) => (
                <tr key={prompt.id}>
                  <td className="small">#{prompt.id}</td>
                  <td>{prompt.input_text.slice(0, 50)}{prompt.input_text.length > 50 ? "..." : ""}</td>
                  <td className="small">{prompt.output_length ?? "-"} chars</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
