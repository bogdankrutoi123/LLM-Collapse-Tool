import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, apiUpload } from "../api/client";
import { BarChart, Bar, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import InsightCallout from "../components/InsightCallout";

type TokenStat = {
  token: string;
  count: number;
  frequency: number;
};

type WikiTextBenchmark = {
  dataset: string;
  dataset_id?: string;
  tokenization: string;
  tokenizer_model_id?: string | null;
  token_count: number;
  vocab_size: number;
  entropy: number;
  perplexity: number;
  rare_token_percentage: number;
  top_tokens: TokenStat[];
  model_id?: string;
  sample_count: number;
  prompts_used: number;
  num_beams?: number;
  avg_sequence_perplexity?: number;
  std_sequence_perplexity?: number;
  reference_entropy?: number;
  reference_perplexity?: number;
  js_divergence?: number;
};

type BenchmarkJobStatus = "queued" | "running" | "completed" | "failed";

type BenchmarkJob = {
  id: number;
  model_version_id: number;
  status: BenchmarkJobStatus;
  error_message: string | null;
  dataset_id: string;
  sample_count: number;
  max_new_tokens: number;
  temperature: number;
  num_beams: number;
  max_tokens: number;
  top_k: number;
  rare_percentile: number;
  seed: number | null;
  result: WikiTextBenchmark | null;
  aggregated_metric_id: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

type DatasetOption = {
  id: string;
  label: string;
};

type DatasetListResponse = {
  datasets: DatasetOption[];
  default_dataset_id: string;
};

type UploadDatasetResponse = {
  status: string;
  dataset: DatasetOption;
};

type Model = {
  id: number;
  name: string;
};

type ModelVersion = {
  id: number;
  model_id: number;
  version: string;
  is_current: boolean;
};

const POLL_INTERVAL_MS = 3000;

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function statusBadgeStyle(status: BenchmarkJobStatus): React.CSSProperties {
  switch (status) {
    case "queued":
      return { background: "#e0e7ff", color: "#3730a3" };
    case "running":
      return { background: "#fef3c7", color: "#92400e" };
    case "completed":
      return { background: "#dcfce7", color: "#166534" };
    case "failed":
      return { background: "#fee2e2", color: "#991b1b" };
  }
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const startMs = new Date(start).getTime();
  const endMs = end ? new Date(end).getTime() : Date.now();
  const diffSec = Math.max(0, Math.round((endMs - startMs) / 1000));
  if (diffSec < 60) return `${diffSec}s`;
  const min = Math.floor(diffSec / 60);
  const sec = diffSec % 60;
  return `${min}m ${sec}s`;
}

export default function Benchmark() {
  const [maxTokens, setMaxTokens] = useState("8000");
  const [topK, setTopK] = useState("20");
  const [rarePercentile, setRarePercentile] = useState("0.1");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [models, setModels] = useState<Model[]>([]);
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [sampleCount, setSampleCount] = useState("8");
  const [maxNewTokens, setMaxNewTokens] = useState("32");
  const [temperature, setTemperature] = useState("0.7");
  const [numBeams, setNumBeams] = useState("1");
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [datasetId, setDatasetId] = useState("wikitext-2");
  const [datasetFile, setDatasetFile] = useState<File | null>(null);

  const [jobs, setJobs] = useState<BenchmarkJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) || null,
    [jobs, selectedJobId]
  );
  const result = selectedJob?.status === "completed" ? selectedJob.result : null;

  const hasActiveJobs = useMemo(
    () => jobs.some((job) => job.status === "queued" || job.status === "running"),
    [jobs]
  );

  const loadJobs = async () => {
    try {
      const data = await apiFetch<BenchmarkJob[]>(
        "/api/v1/analysis/wikitext/benchmark/jobs?limit=50"
      );
      setJobs(data);
      return data;
    } catch (err) {
      setError(getErrorMessage(err));
      return [];
    }
  };

  // initial load
  useEffect(() => {
    apiFetch<Model[]>("/api/v1/models/")
      .then(setModels)
      .catch((error: unknown) => setError(getErrorMessage(error)));

    apiFetch<DatasetListResponse>("/api/v1/analysis/wikitext/datasets")
      .then((res) => {
        setDatasets(res.datasets || []);
        setDatasetId(res.default_dataset_id || "wikitext-2");
      })
      .catch((error: unknown) => setError(getErrorMessage(error)));

    loadJobs();
  }, []);

  // poll only while there are active jobs
  useEffect(() => {
    if (!hasActiveJobs) {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }
    if (pollTimerRef.current !== null) return;
    pollTimerRef.current = window.setInterval(loadJobs, POLL_INTERVAL_MS);
    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [hasActiveJobs]);

  useEffect(() => {
    if (!selectedModelId) {
      setVersions([]);
      setSelectedVersionId("");
      return;
    }
    apiFetch<ModelVersion[]>(`/api/v1/models/${selectedModelId}/versions`)
      .then(setVersions)
      .catch((error: unknown) => setError(getErrorMessage(error)));
  }, [selectedModelId]);

  const handleSubmit = async () => {
    setError(null);
    setInfo(null);
    if (!selectedVersionId) {
      setError("Select a model version to benchmark.");
      return;
    }
    setIsSubmitting(true);
    try {
      const job = await apiFetch<BenchmarkJob>(
        "/api/v1/analysis/wikitext/benchmark",
        {
          method: "POST",
          body: JSON.stringify({
            model_version_id: Number(selectedVersionId),
            dataset_id: datasetId,
            sample_count: Number(sampleCount) || 8,
            max_new_tokens: Number(maxNewTokens) || 32,
            temperature: Number(temperature) || 0.7,
            num_beams: Number(numBeams) || 1,
            max_tokens: Number(maxTokens) || 8000,
            top_k: Number(topK) || 20,
            rare_percentile: Number(rarePercentile) || 0.1,
          }),
        }
      );
      setInfo(`Benchmark job #${job.id} queued. You can leave this page — results will appear when ready.`);
      setSelectedJobId(job.id);
      await loadJobs();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUploadDataset = async () => {
    if (!datasetFile) {
      setError("Select a dataset file first.");
      return;
    }
    setError(null);
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", datasetFile);
      const upload = await apiUpload<UploadDatasetResponse>(
        "/api/v1/analysis/wikitext/datasets/upload",
        formData
      );
      const updated = await apiFetch<DatasetListResponse>("/api/v1/analysis/wikitext/datasets");
      setDatasets(updated.datasets || []);
      if (upload?.dataset?.id) {
        setDatasetId(upload.dataset.id);
      }
      setDatasetFile(null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteJob = async (jobId: number) => {
    if (!window.confirm(`Remove benchmark job #${jobId} from history?`)) return;
    try {
      await apiFetch(`/api/v1/analysis/wikitext/benchmark/jobs/${jobId}`, { method: "DELETE" });
      if (selectedJobId === jobId) setSelectedJobId(null);
      await loadJobs();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const versionLabel = (versionId: number): string => {
    const v = versions.find((ver) => ver.id === versionId);
    if (v) return `${v.version} (#${v.id})`;
    return `#${versionId}`;
  };

  const topTokenChartData = result
    ? result.top_tokens.slice(0, 15).map((item) => ({
        token: item.token,
        frequencyPercent: item.frequency * 100,
      }))
    : [];

  return (
    <div className="grid">
      <div className="card">
        <h2>Model Benchmark</h2>
        <p className="small">
          Submit a benchmark job — it runs in the background on a Celery worker. You can leave this page and come
          back later: the job history below shows progress and lets you open completed runs.
          Metrics include entropy, perplexity, JS divergence and vocabulary statistics relative to the reference corpus.
        </p>
        <div className="form-row">
          <select
            className="input"
            value={datasetId}
            onChange={(event) => setDatasetId(event.target.value)}
          >
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.label}
              </option>
            ))}
          </select>
          <input
            className="input"
            type="file"
            accept=".txt,.csv,.parquet,.jsonl,.json"
            onChange={(event) => setDatasetFile(event.target.files?.[0] || null)}
          />
          <button className="button secondary" onClick={handleUploadDataset} disabled={isUploading}>
            {isUploading ? "Uploading..." : "Upload Dataset"}
          </button>
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
          <select
            className="input"
            value={selectedVersionId}
            onChange={(event) => setSelectedVersionId(event.target.value)}
          >
            <option value="">Select version</option>
            {versions.map((version) => (
              <option key={version.id} value={version.id}>
                {version.version}{version.is_current ? " (current)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <div>
            <label className="small">Max tokens to analyze</label>
            <input className="input" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} placeholder="20000" />
          </div>
          <div>
            <label className="small">Top-K tokens to display</label>
            <input className="input" value={topK} onChange={(event) => setTopK(event.target.value)} placeholder="20" />
          </div>
          <div>
            <label className="small">Rare token percentile</label>
            <input className="input" value={rarePercentile} onChange={(event) => setRarePercentile(event.target.value)} placeholder="0.1" />
          </div>
        </div>
        <div className="form-row">
          <div>
            <label className="small">Sample prompts from dataset</label>
            <input className="input" value={sampleCount} onChange={(event) => setSampleCount(event.target.value)} placeholder="25" />
          </div>
          <div>
            <label className="small">Max new tokens per sample</label>
            <input className="input" value={maxNewTokens} onChange={(event) => setMaxNewTokens(event.target.value)} placeholder="64" />
          </div>
          <div>
            <label className="small">Temperature</label>
            <input className="input" value={temperature} onChange={(event) => setTemperature(event.target.value)} placeholder="0.7" />
          </div>
          <div>
            <label className="small">Beam search size</label>
            <input className="input" value={numBeams} onChange={(event) => setNumBeams(event.target.value)} placeholder="5" />
          </div>
        </div>
        <button className="button" onClick={handleSubmit} disabled={isSubmitting}>
          {isSubmitting ? "Queuing..." : "Submit Benchmark"}
        </button>
        <InsightCallout
          tone="info"
          title="Interpretation"
          text="Higher entropy generally implies richer token distribution, while higher JS divergence against reference may indicate instability or drift."
        />
        {error && <p className="small" style={{ color: "#ef4444" }}>{error}</p>}
        {info && <p className="small" style={{ color: "#166534" }}>{info}</p>}
      </div>

      <div className="card">
        <div className="topbar">
          <h3>Benchmark Jobs</h3>
          <button className="button secondary" onClick={loadJobs}>Refresh</button>
        </div>
        {jobs.length === 0 ? (
          <p className="small">No benchmark jobs yet. Submit one above.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Version</th>
                <th>Dataset</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const isSelected = job.id === selectedJobId;
                return (
                  <tr key={job.id} style={isSelected ? { background: "#f1f5f9" } : {}}>
                    <td>{job.id}</td>
                    <td>{versionLabel(job.model_version_id)}</td>
                    <td>{job.dataset_id}</td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          ...statusBadgeStyle(job.status),
                          textTransform: "uppercase",
                          fontSize: 11,
                        }}
                      >
                        {job.status}
                      </span>
                    </td>
                    <td className="small">{formatDuration(job.started_at, job.completed_at)}</td>
                    <td className="small">{new Date(job.created_at).toLocaleString()}</td>
                    <td>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button
                          className="button secondary"
                          onClick={() => setSelectedJobId(job.id)}
                          disabled={job.status !== "completed" && job.status !== "failed"}
                          title={
                            job.status === "queued" || job.status === "running"
                              ? "Job is still running"
                              : "View results"
                          }
                        >
                          {isSelected ? "Selected" : "View"}
                        </button>
                        <button
                          className="button secondary"
                          style={{ color: "#b91c1c", borderColor: "#fecaca" }}
                          onClick={() => handleDeleteJob(job.id)}
                          disabled={job.status === "running"}
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
        )}
      </div>

      {selectedJob && selectedJob.status === "failed" && (
        <InsightCallout
          tone="warning"
          title={`Benchmark job #${selectedJob.id} failed`}
          text={selectedJob.error_message || "Unknown error. Check the worker logs."}
        />
      )}

      {result && (
        <>
          {result.prompts_used < result.sample_count && (
            <InsightCallout
              tone="warning"
              title="Data Quality Warning"
              text={`Only ${result.prompts_used} of ${result.sample_count} requested prompts were used. Comparative conclusions may be less stable.`}
            />
          )}
          <div className="grid grid-3">
            <div className="card">
              <div className="small">Job</div>
              <strong>#{selectedJob?.id}</strong>
              <div className="small">{selectedJob ? new Date(selectedJob.completed_at || selectedJob.created_at).toLocaleString() : ""}</div>
            </div>
            <div className="card">
              <div className="small">Dataset</div>
              <strong>{result.dataset}</strong>
              {result.dataset_id && <div className="small">{result.dataset_id}</div>}
            </div>
            <div className="card">
              <div className="small">Tokenization</div>
              <strong>{result.tokenization}</strong>
            </div>
            <div className="card">
              <div className="small">Model</div>
              <strong>{result.model_id || "local"}</strong>
              <div className="small">
                Prompts: {result.prompts_used} / {result.sample_count}
              </div>
              {result.num_beams && <div className="small">Beams: {result.num_beams}</div>}
            </div>
            <div className="card">
              <div className="small">Avg Seq Perplexity</div>
              <strong>{(result.avg_sequence_perplexity ?? 0).toFixed(4)}</strong>
            </div>
            <div className="card">
              <div className="small">Std Seq Perplexity</div>
              <strong>{(result.std_sequence_perplexity ?? 0).toFixed(4)}</strong>
            </div>
            <div className="card">
              <div className="small">Reference Entropy</div>
              <strong>{(result.reference_entropy ?? 0).toFixed(4)}</strong>
            </div>
            <div className="card">
              <div className="small">Reference Perplexity</div>
              <strong>{(result.reference_perplexity ?? 0).toFixed(4)}</strong>
            </div>
            <div className="card">
              <div className="small">JS Divergence</div>
              <strong>{(result.js_divergence ?? 0).toFixed(4)}</strong>
            </div>
            <div className="card">
              <div className="small">Token Count</div>
              <strong>{result.token_count.toLocaleString()}</strong>
            </div>
            <div className="card">
              <div className="small">Vocabulary Size</div>
              <strong>{result.vocab_size.toLocaleString()}</strong>
            </div>
            <div className="card">
              <div className="small">Entropy (bits)</div>
              <strong>{result.entropy.toFixed(4)}</strong>
            </div>
            <div className="card">
              <div className="small">Perplexity</div>
              <strong>{result.perplexity.toFixed(4)}</strong>
            </div>
            <div className="card">
              <div className="small">Rare Token %</div>
              <strong>{result.rare_token_percentage.toFixed(2)}%</strong>
            </div>
          </div>

          <div className="card">
            <h3>Top Tokens</h3>
            <div style={{ width: "100%", height: 320, marginBottom: 12 }}>
              <ResponsiveContainer>
                <BarChart data={topTokenChartData} layout="vertical" margin={{ top: 8, right: 12, bottom: 8, left: 12 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tickFormatter={(value: number) => `${value.toFixed(2)}%`} />
                  <YAxis type="category" dataKey="token" width={120} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(value: number) => `${value.toFixed(3)}%`} />
                  <Bar dataKey="frequencyPercent" fill="#2563eb" name="Frequency" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Token</th>
                  <th>Count</th>
                  <th>Frequency</th>
                </tr>
              </thead>
              <tbody>
                {result.top_tokens.map((row, index) => (
                  <tr key={`${row.token}-${index}`}>
                    <td>{row.token}</td>
                    <td>{row.count.toLocaleString()}</td>
                    <td>{(row.frequency * 100).toFixed(3)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
