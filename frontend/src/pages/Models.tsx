import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { Model, ModelVersion } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { canManageModels } from "../auth/permissions";

type ModelStatus = "active" | "archived" | "rollback" | "testing";

export default function Models() {
  const { user } = useAuth();
  const canEditModels = canManageModels(user);
  const [models, setModels] = useState<Model[]>([]);
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [newModelName, setNewModelName] = useState("");
  const [newModelSource, setNewModelSource] = useState("");
  const [newModelDescription, setNewModelDescription] = useState("");
  const [newVersionName, setNewVersionName] = useState("");
  const [newVersionDescription, setNewVersionDescription] = useState("");
  const [newVersionHfId, setNewVersionHfId] = useState("");
  const [newVersionWeightsPath, setNewVersionWeightsPath] = useState("");
  const [editingModelId, setEditingModelId] = useState<number | null>(null);
  const [editingVersionId, setEditingVersionId] = useState<number | null>(null);
  const [modelEditName, setModelEditName] = useState("");
  const [modelEditSource, setModelEditSource] = useState("");
  const [modelEditDescription, setModelEditDescription] = useState("");
  const [modelEditStatus, setModelEditStatus] = useState<ModelStatus>("testing");
  const [versionEditName, setVersionEditName] = useState("");
  const [versionEditDescription, setVersionEditDescription] = useState("");
  const [versionEditHfId, setVersionEditHfId] = useState("");
  const [versionEditWeightsPath, setVersionEditWeightsPath] = useState("");
  const [versionEditIsCurrent, setVersionEditIsCurrent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadModels();
  }, []);

  useEffect(() => {
    if (!selectedModelId) {
      setVersions([]);
      return;
    }
    apiFetch<ModelVersion[]>(`/api/v1/models/${selectedModelId}/versions`)
      .then(setVersions)
      .catch((err) => setError(err.message));
  }, [selectedModelId]);

  function loadModels() {
    apiFetch<Model[]>("/api/v1/models/")
      .then(setModels)
      .catch((err) => setError(err.message));
  }

  async function handleCreateModel() {
    if (!canEditModels) {
      setError("You do not have permission to create models.");
      return;
    }
    setError(null);
    const name = newModelName.trim();
    if (!name) {
      setError("Model name is required.");
      return;
    }
    const payload = {
      name,
      status: "testing",
      description: newModelDescription.trim() || undefined,
      source: newModelSource.trim() || undefined
    };
    try {
      await apiFetch<Model>("/api/v1/models/", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      setNewModelName("");
      setNewModelSource("");
      setNewModelDescription("");
      loadModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create model.");
    }
  }

  async function handleDeleteModel(modelId: number) {
    if (!canEditModels) {
      setError("You do not have permission to delete models.");
      return;
    }
    const model = models.find((item) => item.id === modelId);
    const label = model ? `"${model.name}"` : `#${modelId}`;
    if (!window.confirm(`Delete model ${label}? This cannot be undone.`)) {
      return;
    }
    setError(null);
    try {
      await apiFetch(`/api/v1/models/${modelId}`, { method: "DELETE" });
      if (String(modelId) === selectedModelId) {
        setSelectedModelId("");
        setVersions([]);
      }
      loadModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete model.");
    }
  }

  function startEditModel(model: Model) {
    setEditingModelId(model.id);
    setModelEditName(model.name || "");
    setModelEditSource(model.source || "");
    setModelEditDescription(model.description || "");
    setModelEditStatus((model.status as ModelStatus) || "testing");
  }

  function cancelEditModel() {
    setEditingModelId(null);
  }

  async function saveEditModel(modelId: number) {
    if (!canEditModels) {
      setError("You do not have permission to update models.");
      return;
    }
    setError(null);
    const name = modelEditName.trim();
    if (!name) {
      setError("Model name is required.");
      return;
    }
    try {
      await apiFetch<Model>(`/api/v1/models/${modelId}`, {
        method: "PUT",
        body: JSON.stringify({
          name,
          source: modelEditSource.trim() || null,
          description: modelEditDescription.trim() || null,
          status: modelEditStatus
        })
      });
      setEditingModelId(null);
      loadModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update model.");
    }
  }

  async function handleCreateVersion() {
    if (!canEditModels) {
      setError("You do not have permission to create model versions.");
      return;
    }
    setError(null);
    if (!selectedModelId) {
      setError("Select a model before adding a version.");
      return;
    }
    const version = newVersionName.trim();
    if (!version) {
      setError("Version name is required.");
      return;
    }
    const metadata = newVersionHfId.trim()
      ? { hf_model_id: newVersionHfId.trim() }
      : undefined;
    const weightsPath = newVersionWeightsPath.trim() || undefined;
    const payload = {
      model_id: Number(selectedModelId),
      version,
      description: newVersionDescription.trim() || undefined,
      model_metadata: metadata,
      weights_path: weightsPath
    };
    try {
      await apiFetch<ModelVersion>(`/api/v1/models/${selectedModelId}/versions`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      setNewVersionName("");
      setNewVersionDescription("");
      setNewVersionHfId("");
      setNewVersionWeightsPath("");
      const refreshed = await apiFetch<ModelVersion[]>(
        `/api/v1/models/${selectedModelId}/versions`
      );
      setVersions(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create version.");
    }
  }

  async function handleDeleteVersion(versionId: number) {
    if (!canEditModels) {
      setError("You do not have permission to delete model versions.");
      return;
    }
    if (!window.confirm(`Delete version #${versionId}?`)) {
      return;
    }
    setError(null);
    try {
      await apiFetch(`/api/v1/models/versions/${versionId}`, { method: "DELETE" });
      if (selectedModelId) {
        const refreshed = await apiFetch<ModelVersion[]>(
          `/api/v1/models/${selectedModelId}/versions`
        );
        setVersions(refreshed);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete version.");
    }
  }

  function startEditVersion(version: ModelVersion) {
    setEditingVersionId(version.id);
    setVersionEditName(version.version || "");
    setVersionEditDescription(version.description || "");
    setVersionEditHfId(version.metadata?.hf_model_id || "");
    setVersionEditWeightsPath(version.weights_path || "");
    setVersionEditIsCurrent(Boolean(version.is_current));
  }

  function cancelEditVersion() {
    setEditingVersionId(null);
  }

  async function saveEditVersion(versionId: number) {
    if (!canEditModels) {
      setError("You do not have permission to update model versions.");
      return;
    }
    setError(null);
    const versionName = versionEditName.trim();
    if (!versionName) {
      setError("Version name is required.");
      return;
    }
    const metadata = versionEditHfId.trim() ? { hf_model_id: versionEditHfId.trim() } : null;
    try {
      await apiFetch<ModelVersion>(`/api/v1/models/versions/${versionId}`, {
        method: "PUT",
        body: JSON.stringify({
          version: versionName,
          description: versionEditDescription.trim() || null,
          model_metadata: metadata,
          weights_path: versionEditWeightsPath.trim() || null,
          is_current: versionEditIsCurrent
        })
      });
      setEditingVersionId(null);
      if (selectedModelId) {
        const refreshed = await apiFetch<ModelVersion[]>(`/api/v1/models/${selectedModelId}/versions`);
        setVersions(refreshed);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update model version.");
    }
  }

  return (
    <div className="grid">
      <div className="card">
        <div className="topbar">
          <h2>Models</h2>
        </div>
        {error && <p className="small">{error}</p>}
        {canEditModels && (
          <>
            <div className="form-row">
              <input
                className="input"
                value={newModelName}
                onChange={(event) => setNewModelName(event.target.value)}
                placeholder="Model name"
              />
              <input
                className="input"
                value={newModelSource}
                onChange={(event) => setNewModelSource(event.target.value)}
                placeholder="Source (optional)"
              />
            </div>
            <div className="form-row">
              <input
                className="input"
                value={newModelDescription}
                onChange={(event) => setNewModelDescription(event.target.value)}
                placeholder="Description (optional)"
              />
              <button className="button" onClick={handleCreateModel}>
                Add model
              </button>
            </div>
          </>
        )}
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Description</th>
              <th>Source</th>
              <th>Status</th>
              <th>Created</th>
              {canEditModels && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr key={model.id}>
                <td>{model.id}</td>
                {editingModelId === model.id ? (
                  <>
                    <td>
                      <input className="input" value={modelEditName} onChange={(event) => setModelEditName(event.target.value)} />
                    </td>
                    <td>
                      <input className="input" value={modelEditDescription} onChange={(event) => setModelEditDescription(event.target.value)} />
                    </td>
                    <td>
                      <input className="input" value={modelEditSource} onChange={(event) => setModelEditSource(event.target.value)} />
                    </td>
                    <td>
                      <select className="input" value={modelEditStatus} onChange={(event) => setModelEditStatus(event.target.value as ModelStatus)}>
                        <option value="testing">testing</option>
                        <option value="active">active</option>
                        <option value="archived">archived</option>
                        <option value="rollback">rollback</option>
                      </select>
                    </td>
                  </>
                ) : (
                  <>
                    <td>{model.name}</td>
                    <td>{model.description || "-"}</td>
                    <td>{model.source || "-"}</td>
                    <td>{model.status || "-"}</td>
                  </>
                )}
                <td>{new Date(model.created_at).toLocaleString()}</td>
                {canEditModels && (
                  <td>
                    {editingModelId === model.id ? (
                      <div style={{ display: "flex", gap: "8px" }}>
                        <button className="button" onClick={() => saveEditModel(model.id)}>Save</button>
                        <button className="button secondary" onClick={cancelEditModel}>Cancel</button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: "8px" }}>
                        <button className="button secondary" onClick={() => startEditModel(model)}>Edit</button>
                        <button className="button secondary" onClick={() => handleDeleteModel(model.id)}>Delete</button>
                      </div>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <div className="topbar">
          <h2>Model Versions</h2>
        </div>
        <div className="form-row">
          <select
            className="input"
            value={selectedModelId}
            onChange={(event) => setSelectedModelId(event.target.value)}
          >
            <option value="">Select model</option>
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
          {canEditModels && (
            <>
              <input
                className="input"
                value={newVersionName}
                onChange={(event) => setNewVersionName(event.target.value)}
                placeholder="Version name"
              />
              <input
                className="input"
                value={newVersionHfId}
                onChange={(event) => setNewVersionHfId(event.target.value)}
                placeholder="HF model ID (e.g. microsoft/phi-1_5)"
                title="HuggingFace model identifier used for benchmarking"
              />
              <input
                className="input"
                value={newVersionWeightsPath}
                onChange={(event) => setNewVersionWeightsPath(event.target.value)}
                placeholder="Local weights path (e.g. /models/my_model or C:/models/my_model)"
                title="Local filesystem path to model weights for benchmark loading"
              />
            </>
          )}
        </div>
        {canEditModels && (
          <div className="form-row">
            <input
              className="input"
              value={newVersionDescription}
              onChange={(event) => setNewVersionDescription(event.target.value)}
              placeholder="Version description (optional)"
            />
            <button className="button" onClick={handleCreateVersion}>
              Add version
            </button>
          </div>
        )}
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Version</th>
              <th>Description</th>
              <th>HF Model</th>
              <th>Local Path</th>
              <th>Current</th>
              <th>Deployed</th>
              {canEditModels && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {versions.map((version) => (
              <tr key={version.id}>
                <td>{version.id}</td>
                {editingVersionId === version.id ? (
                  <>
                    <td>
                      <input className="input" value={versionEditName} onChange={(event) => setVersionEditName(event.target.value)} />
                    </td>
                    <td>
                      <input className="input" value={versionEditDescription} onChange={(event) => setVersionEditDescription(event.target.value)} />
                    </td>
                    <td>
                      <input className="input" value={versionEditHfId} onChange={(event) => setVersionEditHfId(event.target.value)} />
                    </td>
                    <td>
                      <input className="input" value={versionEditWeightsPath} onChange={(event) => setVersionEditWeightsPath(event.target.value)} />
                    </td>
                    <td>
                      <label className="small" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <input type="checkbox" checked={versionEditIsCurrent} onChange={(event) => setVersionEditIsCurrent(event.target.checked)} />
                        current
                      </label>
                    </td>
                  </>
                ) : (
                  <>
                    <td>{version.version}</td>
                    <td>{version.description || "-"}</td>
                    <td>{version.metadata?.hf_model_id || "-"}</td>
                    <td>{version.weights_path || "-"}</td>
                    <td>{version.is_current ? "Yes" : "No"}</td>
                  </>
                )}
                <td>{new Date(version.deployment_date).toLocaleString()}</td>
                {canEditModels && (
                  <td>
                    {editingVersionId === version.id ? (
                      <div style={{ display: "flex", gap: "8px" }}>
                        <button className="button" onClick={() => saveEditVersion(version.id)}>Save</button>
                        <button className="button secondary" onClick={cancelEditVersion}>Cancel</button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: "8px" }}>
                        <button className="button secondary" onClick={() => startEditVersion(version)}>Edit</button>
                        <button className="button secondary" onClick={() => handleDeleteVersion(version.id)}>Delete</button>
                      </div>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
