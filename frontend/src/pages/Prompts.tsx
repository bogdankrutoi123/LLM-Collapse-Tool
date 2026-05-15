import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api/client";
import { Prompt, Model, ModelVersion } from "../api/types";

export default function Prompts() {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [selectedPromptId, setSelectedPromptId] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [newModelId, setNewModelId] = useState("");
  const [newVersionId, setNewVersionId] = useState("");
  const [newInputText, setNewInputText] = useState("");
  const [newTemperature, setNewTemperature] = useState("0.7");

  const [editingPromptId, setEditingPromptId] = useState<number | null>(null);
  const [editInputText, setEditInputText] = useState("");
  const [editTemperature, setEditTemperature] = useState("");
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  const selectedPrompt = useMemo(
    () => prompts.find((prompt) => prompt.id === selectedPromptId) || null,
    [prompts, selectedPromptId]
  );

  const loadPrompts = async () => {
    try {
      const data = await apiFetch<Prompt[]>("/api/v1/prompts/?limit=50");
      setPrompts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load prompts");
    }
  };

  useEffect(() => {
    loadPrompts();
    apiFetch<Model[]>("/api/v1/models/")
      .then(setModels)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!newModelId) {
      setVersions([]);
      setNewVersionId("");
      return;
    }
    apiFetch<ModelVersion[]>(`/api/v1/models/${newModelId}/versions`)
      .then(setVersions)
      .catch((err) => setError(err.message));
  }, [newModelId]);

  useEffect(() => {
    setActionMessage(null);
    setMetrics(null);
  }, [selectedPromptId]);

  const handleCreatePrompt = async () => {
    setError(null);
    if (!newVersionId) {
      setError("Select a model and version first.");
      return;
    }
    if (!newInputText.trim()) {
      setError("Enter prompt text.");
      return;
    }
    const temperature = Number(newTemperature) || 0.7;
    setIsSubmitting(true);
    try {
      const created = await apiFetch<Prompt>("/api/v1/prompts/", {
        method: "POST",
        body: JSON.stringify({
          model_version_id: Number(newVersionId),
          input_text: newInputText.trim(),
          temperature,
          max_new_tokens: 128
        })
      });
      // auto-generate immediately after creation
      const generated = await apiFetch<Prompt>(
        `/api/v1/prompts/${created.id}/generate`,
        {
          method: "POST",
          body: JSON.stringify({
            max_new_tokens: 128,
            temperature
          })
        }
      );
      setNewInputText("");
      // refresh list so selectedPrompt resolves after setSelectedPromptId
      await loadPrompts();
      setSelectedPromptId(generated.id);
      setActionMessage("Prompt created and generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create prompt.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStartEdit = (prompt: Prompt) => {
    setEditingPromptId(prompt.id);
    setEditInputText(prompt.input_text);
    setEditTemperature(prompt.temperature?.toString() ?? "");
    setError(null);
    setActionMessage(null);
  };

  const handleCancelEdit = () => {
    setEditingPromptId(null);
    setEditInputText("");
    setEditTemperature("");
  };

  const handleSaveEdit = async () => {
    if (editingPromptId === null) return;
    if (!editInputText.trim()) {
      setError("Prompt text cannot be empty.");
      return;
    }
    setError(null);
    setIsSavingEdit(true);
    try {
      const tempNum = editTemperature ? Number(editTemperature) : NaN;
      const payload: Record<string, unknown> = { input_text: editInputText.trim() };
      if (Number.isFinite(tempNum)) payload.temperature = tempNum;

      await apiFetch<Prompt>(`/api/v1/prompts/${editingPromptId}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      });

      // input changed — previous output is stale, regenerate
      const regenerated = await apiFetch<Prompt>(
        `/api/v1/prompts/${editingPromptId}/generate`,
        {
          method: "POST",
          body: JSON.stringify({
            max_new_tokens: 128,
            temperature: Number.isFinite(tempNum) ? tempNum : 0.7
          })
        }
      );
      setSelectedPromptId(regenerated.id);
      setEditingPromptId(null);
      setEditInputText("");
      setEditTemperature("");
      setActionMessage("Prompt updated and regenerated.");
      loadPrompts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update prompt.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleDelete = async (promptId: number) => {
    if (!window.confirm(`Delete prompt #${promptId}? This cannot be undone.`)) return;
    setError(null);
    try {
      await apiFetch(`/api/v1/prompts/${promptId}`, { method: "DELETE" });
      if (selectedPromptId === promptId) setSelectedPromptId(null);
      if (editingPromptId === promptId) handleCancelEdit();
      setActionMessage(`Prompt #${promptId} deleted.`);
      loadPrompts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete prompt.");
    }
  };

  const handleCalculateMetrics = async () => {
    if (!selectedPrompt) return;
    setActionMessage(null);
    try {
      const metric = await apiFetch<Record<string, unknown>>(
        `/api/v1/prompts/${selectedPrompt.id}/metrics`,
        { method: "POST" }
      );
      setMetrics(metric);
      setActionMessage("Metrics calculated.");
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Failed to calculate metrics.");
    }
  };

  const handleLoadMetrics = async () => {
    if (!selectedPrompt) return;
    setActionMessage(null);
    try {
      const metric = await apiFetch<Record<string, unknown>>(
        `/api/v1/prompts/${selectedPrompt.id}/metrics`
      );
      setMetrics(metric);
      setActionMessage("Metrics loaded.");
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "No metrics found.");
    }
  };

  const metricKeys: { key: string; label: string }[] = [
    { key: "entropy", label: "Entropy" },
    { key: "kl_divergence", label: "KL Divergence" },
    { key: "js_divergence", label: "JS Divergence" },
    { key: "wasserstein_distance", label: "Wasserstein Dist." },
    { key: "ngram_drift", label: "N-gram Drift" },
    { key: "embedding_drift", label: "Embedding Drift" },
    { key: "rare_token_percentage", label: "Rare Token %" },
    { key: "new_token_percentage", label: "New Token %" },
    { key: "median_length", label: "Median Length" },
    { key: "length_variance", label: "Length Variance" }
  ];

  const formatVal = (val: unknown): string => {
    if (val === null || val === undefined) return "—";
    if (typeof val === "number") return val.toFixed(4);
    return String(val);
  };

  return (
    <div className="grid">
      <div className="card">
        <h2>Manual Prompt Debugging</h2>
        <p className="small">
          Debug-only flow. For production analysis, use the Benchmark and Analysis pages to run dataset-based checks and compare versions.
          This screen is intended for ad-hoc troubleshooting and single prompt experiments.
        </p>
        {error && <p className="small" style={{color: "#ef4444"}}>{error}</p>}
        <div className="form-row">
          <div>
            <label className="small">Model</label>
            <select className="input" value={newModelId} onChange={(e) => setNewModelId(e.target.value)}>
              <option value="">Select model</option>
              {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
          <div>
            <label className="small">Version</label>
            <select className="input" value={newVersionId} onChange={(e) => setNewVersionId(e.target.value)}>
              <option value="">Select version</option>
              {versions.map((v) => <option key={v.id} value={v.id}>{v.version}{v.is_current ? " (current)" : ""}</option>)}
            </select>
          </div>
          <div>
            <label className="small">Temperature</label>
            <input className="input" value={newTemperature} onChange={(e) => setNewTemperature(e.target.value)} />
          </div>
        </div>
        <div style={{marginTop: "8px"}}>
          <label className="small">Prompt text</label>
          <textarea
            className="input"
            rows={3}
            value={newInputText}
            onChange={(e) => setNewInputText(e.target.value)}
            placeholder="Enter your prompt here..."
          />
        </div>
        <div style={{marginTop: "8px"}}>
          <button className="button" onClick={handleCreatePrompt} disabled={isSubmitting}>
            {isSubmitting ? "Generating..." : "Submit & Generate"}
          </button>
        </div>
      </div>

      <div className="card">
        <div className="topbar">
          <h2>Prompts</h2>
          <button className="button secondary" onClick={loadPrompts}>Refresh</button>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Version</th>
              <th>Input</th>
              <th>Output</th>
              <th>Submitted</th>
              <th style={{minWidth: 220}}></th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => {
              const isEditing = editingPromptId === prompt.id;
              if (isEditing) {
                return (
                  <tr key={prompt.id} style={{background: "#fefce8"}}>
                    <td>{prompt.id}</td>
                    <td>{prompt.model_version_id}</td>
                    <td colSpan={3}>
                      <textarea
                        className="input"
                        rows={2}
                        value={editInputText}
                        onChange={(e) => setEditInputText(e.target.value)}
                      />
                      <div className="form-row" style={{marginTop: 6}}>
                        <div>
                          <label className="small">Temperature</label>
                          <input
                            className="input"
                            value={editTemperature}
                            onChange={(e) => setEditTemperature(e.target.value)}
                            placeholder="0.7"
                          />
                        </div>
                      </div>
                    </td>
                    <td>
                      <div style={{display: "flex", gap: 6, flexWrap: "wrap"}}>
                        <button className="button" onClick={handleSaveEdit} disabled={isSavingEdit}>
                          {isSavingEdit ? "Saving..." : "Save & Regenerate"}
                        </button>
                        <button className="button secondary" onClick={handleCancelEdit} disabled={isSavingEdit}>
                          Cancel
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              }
              return (
                <tr key={prompt.id} style={prompt.id === selectedPromptId ? {background: "#f1f5f9"} : {}}>
                  <td>{prompt.id}</td>
                  <td>{prompt.model_version_id}</td>
                  <td title={prompt.input_text}>{prompt.input_text.slice(0, 50)}{prompt.input_text.length > 50 ? "..." : ""}</td>
                  <td>{prompt.output_length ? `${prompt.output_length} chars` : "—"}</td>
                  <td className="small">{new Date(prompt.submitted_at).toLocaleString()}</td>
                  <td>
                    <div style={{display: "flex", gap: 6, flexWrap: "wrap"}}>
                      <button className="button secondary" onClick={() => setSelectedPromptId(prompt.id)}>
                        {prompt.id === selectedPromptId ? "Selected" : "Select"}
                      </button>
                      <button className="button secondary" onClick={() => handleStartEdit(prompt)}>
                        Edit
                      </button>
                      <button
                        className="button secondary"
                        style={{color: "#b91c1c", borderColor: "#fecaca"}}
                        onClick={() => handleDelete(prompt.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selectedPrompt && (
        <div className="card">
          <div className="topbar">
            <h2>Prompt #{selectedPrompt.id}</h2>
            {actionMessage && <span className="badge">{actionMessage}</span>}
          </div>
          <div className="grid">
            <div>
              <label className="small">Input text</label>
              <pre className="small" style={{ whiteSpace: "pre-wrap", background: "#f8fafc", padding: "8px", borderRadius: "6px" }}>{selectedPrompt.input_text}</pre>
            </div>
            <div>
              <label className="small">Generated output</label>
              <pre
                className="small"
                style={{
                  whiteSpace: "pre-wrap",
                  background: "#f8fafc",
                  padding: "8px",
                  borderRadius: "6px",
                  minHeight: 60,
                }}
              >
                {selectedPrompt.output_text || "— (no output yet)"}
              </pre>
              {selectedPrompt.generation_time_ms !== null && selectedPrompt.generation_time_ms !== undefined && (
                <p className="small" style={{marginTop: 4}}>
                  Generation time: {selectedPrompt.generation_time_ms.toFixed(1)} ms
                  {selectedPrompt.output_length ? ` · ${selectedPrompt.output_length} chars` : ""}
                </p>
              )}
            </div>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              <button className="button secondary" onClick={handleCalculateMetrics}>Calculate Metrics</button>
              <button className="button secondary" onClick={handleLoadMetrics}>Load Metrics</button>
            </div>
            {metrics && (
              <div>
                <label className="small">Computed Metrics</label>
                <div className="grid grid-3" style={{marginTop: "8px"}}>
                  {metricKeys.map(({key, label}) => {
                    const val = (metrics as Record<string, unknown>)[key];
                    if (val === null || val === undefined) return null;
                    return (
                      <div key={key} className="card" style={{padding: "10px"}}>
                        <div className="small">{label}</div>
                        <strong>{formatVal(val)}</strong>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
