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
  const [outputText, setOutputText] = useState("");
  const [generationTimeMs, setGenerationTimeMs] = useState("");
  const [cpuTimeMs, setCpuTimeMs] = useState("");
  const [gpuTimeMs, setGpuTimeMs] = useState("");
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);

  const [newModelId, setNewModelId] = useState("");
  const [newVersionId, setNewVersionId] = useState("");
  const [newInputText, setNewInputText] = useState("");
  const [newTemperature, setNewTemperature] = useState("0.7");

  const selectedPrompt = useMemo(
    () => prompts.find((prompt) => prompt.id === selectedPromptId) || null,
    [prompts, selectedPromptId]
  );

  const loadPrompts = () => {
    apiFetch<Prompt[]>("/api/v1/prompts/?limit=50")
      .then(setPrompts)
      .catch((err) => setError(err.message));
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
    if (!selectedPrompt) {
      setOutputText("");
      setGenerationTimeMs("");
      setCpuTimeMs("");
      setGpuTimeMs("");
      return;
    }
    setOutputText(selectedPrompt.output_text ?? "");
    setGenerationTimeMs(selectedPrompt.generation_time_ms?.toString() ?? "");
    setCpuTimeMs(selectedPrompt.cpu_time_ms?.toString() ?? "");
    setGpuTimeMs(selectedPrompt.gpu_time_ms?.toString() ?? "");
  }, [selectedPrompt]);

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
    try {
      const created = await apiFetch<Prompt>("/api/v1/prompts/", {
        method: "POST",
        body: JSON.stringify({
          model_version_id: Number(newVersionId),
          input_text: newInputText.trim(),
          temperature: Number(newTemperature) || 0.7,
          max_new_tokens: 128
        })
      });
      setNewInputText("");
      setSelectedPromptId(created.id);
      loadPrompts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create prompt.");
    }
  };

  const handleSaveResponse = async () => {
    if (!selectedPrompt) return;
    setActionMessage(null);
    try {
      const updated = await apiFetch<Prompt>(
        `/api/v1/prompts/${selectedPrompt.id}/response`,
        { method: "PUT", body: JSON.stringify({
          output_text: outputText,
          generation_time_ms: generationTimeMs ? Number(generationTimeMs) : undefined,
          cpu_time_ms: cpuTimeMs ? Number(cpuTimeMs) : undefined,
          gpu_time_ms: gpuTimeMs ? Number(gpuTimeMs) : undefined
        }) }
      );
      setActionMessage("Response saved.");
      setPrompts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Failed to save.");
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
          <button className="button" onClick={handleCreatePrompt}>Submit Prompt</button>
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
              <th></th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => (
              <tr key={prompt.id} style={prompt.id === selectedPromptId ? {background: "#f1f5f9"} : {}}>
                <td>{prompt.id}</td>
                <td>{prompt.model_version_id}</td>
                <td title={prompt.input_text}>{prompt.input_text.slice(0, 50)}{prompt.input_text.length > 50 ? "..." : ""}</td>
                <td>{prompt.output_length ? `${prompt.output_length} chars` : "—"}</td>
                <td className="small">{new Date(prompt.submitted_at).toLocaleString()}</td>
                <td>
                  <button className="button secondary" onClick={() => setSelectedPromptId(prompt.id)}>
                    {prompt.id === selectedPromptId ? "Selected" : "Select"}
                  </button>
                </td>
              </tr>
            ))}
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
              <label className="small">Output text</label>
              <textarea className="input" rows={5} value={outputText} onChange={(e) => setOutputText(e.target.value)} placeholder="Paste model output here..." />
            </div>
            <div className="form-row">
              <div>
                <label className="small">Generation time (ms)</label>
                <input className="input" value={generationTimeMs} onChange={(e) => setGenerationTimeMs(e.target.value)} />
              </div>
              <div>
                <label className="small">CPU time (ms)</label>
                <input className="input" value={cpuTimeMs} onChange={(e) => setCpuTimeMs(e.target.value)} />
              </div>
              <div>
                <label className="small">GPU time (ms)</label>
                <input className="input" value={gpuTimeMs} onChange={(e) => setGpuTimeMs(e.target.value)} />
              </div>
            </div>
            <div style={{ display: "flex", gap: "10px" }}>
              <button className="button" onClick={handleSaveResponse}>Save Response</button>
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
