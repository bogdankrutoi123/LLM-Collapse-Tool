import { useEffect, useState } from "react";
import { createRule, deleteRule, listRules, replaceRuleItems, updateRule } from "../api/admin";
import { AlertRule, AlertRuleItem, ComparisonOperator, RuleOperator } from "../api/types";
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

export default function Rules() {
  const { user } = useAuth();
  const hasRulesAccess = canViewRules(user);

  const [rules, setRules] = useState<AlertRule[]>([]);
  const [name, setName] = useState("");
  const [operator, setOperator] = useState<RuleOperator>("any");
  const [items, setItems] = useState<AlertRuleItem[]>([
    {
      metric_name: "kl_divergence",
      threshold_value: 0.3,
      comparison_operator: ">",
      persistence_count: 1,
      persistence_window_minutes: 0,
    },
  ]);
  const [error, setError] = useState<string | null>(null);

  const fetchRules = async () => {
    try {
      setError(null);
      setRules(await listRules());
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  useEffect(() => {
    if (!hasRulesAccess) {
      return;
    }
    void fetchRules();
  }, [hasRulesAccess]);

  const addItem = () => {
    setItems((prev) => [
      ...prev,
      {
        metric_name: "entropy",
        threshold_value: 0.5,
        comparison_operator: ">",
        persistence_count: 1,
        persistence_window_minutes: 0,
      },
    ]);
  };

  const updateItem = (index: number, patch: Partial<AlertRuleItem>) => {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  const createRuleHandler = async () => {
    if (!hasRulesAccess) {
      setError("You do not have permission to create alert rules.");
      return;
    }
    const normalizedName = name.trim();
    if (!normalizedName) {
      setError("Rule name is required.");
      return;
    }

    try {
      setError(null);
      const created = await createRule({
        name: normalizedName,
        operator,
        items,
        is_active: true,
      });
      if (created.items.length !== items.length) {
        await replaceRuleItems(created.id, items);
      }
      setName("");
      setItems([
        {
          metric_name: "kl_divergence",
          threshold_value: 0.3,
          comparison_operator: ">",
          persistence_count: 1,
          persistence_window_minutes: 0,
        },
      ]);
      await fetchRules();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const toggleRule = async (rule: AlertRule) => {
    try {
      setError(null);
      await updateRule(rule.id, { is_active: !rule.is_active });
      await fetchRules();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const removeRule = async (ruleId: number) => {
    if (!window.confirm(`Delete rule #${ruleId}?`)) {
      return;
    }
    try {
      setError(null);
      await deleteRule(ruleId);
      await fetchRules();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  if (!hasRulesAccess) {
    return (
      <div className="card">
        <h2>Multi-signal Rules</h2>
        <p className="small">Only admin users can view and manage alert rules.</p>
      </div>
    );
  }

  return (
    <div className="grid">
      <div className="card">
        <h2>Multi-signal Rules</h2>
        {error && <p className="small">{error}</p>}
        <div className="form-row">
          <input className="input" placeholder="Rule name" value={name} onChange={(event) => setName(event.target.value)} />
          <select className="input" value={operator} onChange={(event) => setOperator(event.target.value as RuleOperator)}>
            <option value="any">OR (any)</option>
            <option value="all">AND (all)</option>
          </select>
          <button className="button" onClick={() => void createRuleHandler()}>Create</button>
        </div>
        <div className="grid">
          {items.map((item, index) => (
            <div key={index} className="card">
              <div className="form-row">
                <div>
                  <label className="small">Metric name</label>
                  <select
                    className="input"
                    value={item.metric_name}
                    onChange={(event) => updateItem(index, { metric_name: event.target.value })}
                  >
                    {METRIC_OPTIONS.map((metric) => (
                      <option key={metric} value={metric}>{metric}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="small">Threshold value</label>
                  <input
                    className="input"
                    type="number"
                    step="0.01"
                    value={item.threshold_value}
                    onChange={(event) => updateItem(index, { threshold_value: Number(event.target.value) })}
                  />
                </div>
                <div>
                  <label className="small">Operator</label>
                  <select
                    className="input"
                    value={item.comparison_operator}
                    onChange={(event) => updateItem(index, { comparison_operator: event.target.value as ComparisonOperator })}
                  >
                    {COMPARISON_OPERATORS.map((op) => (
                      <option key={op} value={op}>{op}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="form-row">
                <div>
                  <label className="small">Consecutive prompts</label>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    value={item.persistence_count}
                    onChange={(event) => updateItem(index, { persistence_count: Number(event.target.value) || 1 })}
                  />
                </div>
                <div>
                  <label className="small">Time window (min)</label>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    value={item.persistence_window_minutes}
                    onChange={(event) => updateItem(index, { persistence_window_minutes: Number(event.target.value) || 0 })}
                  />
                </div>
                <div style={{ display: "flex", alignItems: "flex-end" }}>
                  <button className="button secondary" onClick={() => setItems((prev) => prev.filter((_, i) => i !== index))}>Remove</button>
                </div>
              </div>
            </div>
          ))}
        </div>
        <button className="button secondary" onClick={addItem}>Add signal</button>
      </div>

      <div className="card">
        <h3>Existing Rules</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Operator</th>
              <th>Active</th>
              <th>Signals</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td>{rule.name}</td>
                <td>{rule.operator}</td>
                <td>{rule.is_active ? "Yes" : "No"}</td>
                <td>{rule.items.length}</td>
                <td>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="button secondary" onClick={() => void toggleRule(rule)}>
                      {rule.is_active ? "Disable" : "Enable"}
                    </button>
                    <button className="button secondary" onClick={() => void removeRule(rule.id)}>Delete</button>
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
