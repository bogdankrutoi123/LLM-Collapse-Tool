import { useEffect, useState } from "react";
import { createThreshold, deleteThreshold, listThresholds, updateThreshold } from "../api/admin";
import { AlertThreshold, ComparisonOperator } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { canViewRules } from "../auth/permissions";

const METRIC_OPTIONS: string[] = [
  "entropy",
  "kl_divergence",
  "js_divergence",
  "wasserstein_distance",
  "ngram_drift",
  "embedding_drift",
  "rare_token_percentage",
  "new_token_percentage",
  "output_length",
  "generation_time_ms",
  "cpu_time_ms",
  "gpu_time_ms",
];

const COMPARISON_OPERATORS: ComparisonOperator[] = [">", "<", ">=", "<=", "=="];

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

export default function AdminThresholds() {
  const { user } = useAuth();
  const isAdmin = canViewRules(user);

  const [thresholds, setThresholds] = useState<AlertThreshold[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [metric, setMetric] = useState("entropy");
  const [operator, setOperator] = useState<ComparisonOperator>(">");
  const [thresholdValue, setThresholdValue] = useState("0.5");
  const [persistenceCount, setPersistenceCount] = useState("1");
  const [windowMinutes, setWindowMinutes] = useState("0");
  const [groupKey, setGroupKey] = useState("");
  const [requireAll, setRequireAll] = useState(false);

  const load = async () => {
    try {
      setError(null);
      setThresholds(await listThresholds());
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  useEffect(() => {
    if (!isAdmin) {
      return;
    }
    void load();
  }, [isAdmin]);

  const handleCreate = async () => {
    const normalizedName = name.trim();
    if (!normalizedName) {
      setError("Threshold name is required.");
      return;
    }

    try {
      setError(null);
      await createThreshold({
        name: normalizedName,
        metric_name: metric,
        threshold_value: Number(thresholdValue),
        comparison_operator: operator,
        persistence_count: Math.max(1, Number(persistenceCount) || 1),
        persistence_window_minutes: Math.max(0, Number(windowMinutes) || 0),
        group_key: groupKey.trim() || undefined,
        require_all_in_group: requireAll,
        is_active: true,
      });
      setName("");
      setGroupKey("");
      setRequireAll(false);
      await load();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const handleToggleActive = async (item: AlertThreshold) => {
    try {
      setError(null);
      await updateThreshold(item.id, { is_active: !item.is_active });
      await load();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const handleDelete = async (thresholdId: number) => {
    if (!window.confirm(`Delete threshold #${thresholdId}?`)) {
      return;
    }
    try {
      setError(null);
      await deleteThreshold(thresholdId);
      await load();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  if (!isAdmin) {
    return (
      <div className="card">
        <h2>Alert Thresholds</h2>
        <p className="small">Only admin users can manage thresholds.</p>
      </div>
    );
  }

  return (
    <div className="grid">
      <div className="card">
        <h2>Alert Thresholds</h2>
        {error && <p className="small">{error}</p>}
        <div className="grid">
          <div className="form-row">
            <input className="input" placeholder="Threshold name" value={name} onChange={(event) => setName(event.target.value)} />
            <select className="input" value={metric} onChange={(event) => setMetric(event.target.value)}>
              {METRIC_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <select className="input" value={operator} onChange={(event) => setOperator(event.target.value as ComparisonOperator)}>
              {COMPARISON_OPERATORS.map((op) => (
                <option key={op} value={op}>{op}</option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <input className="input" type="number" step="0.01" value={thresholdValue} onChange={(event) => setThresholdValue(event.target.value)} placeholder="Threshold value" />
            <input className="input" type="number" min={1} value={persistenceCount} onChange={(event) => setPersistenceCount(event.target.value)} placeholder="Persistence count" />
            <input className="input" type="number" min={0} value={windowMinutes} onChange={(event) => setWindowMinutes(event.target.value)} placeholder="Window minutes" />
          </div>
          <div className="form-row">
            <input className="input" value={groupKey} onChange={(event) => setGroupKey(event.target.value)} placeholder="Group key (optional)" />
            <label className="small" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={requireAll} onChange={(event) => setRequireAll(event.target.checked)} />
              Require all in group
            </label>
            <button className="button" onClick={() => void handleCreate()}>Create threshold</button>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Configured Thresholds</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Metric</th>
              <th>Condition</th>
              <th>Group</th>
              <th>Active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {thresholds.map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>{item.metric_name}</td>
                <td>{item.comparison_operator} {item.threshold_value}</td>
                <td>{item.group_key || "-"}</td>
                <td>{item.is_active ? "Yes" : "No"}</td>
                <td>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="button secondary" onClick={() => void handleToggleActive(item)}>
                      {item.is_active ? "Disable" : "Enable"}
                    </button>
                    <button className="button secondary" onClick={() => void handleDelete(item.id)}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
