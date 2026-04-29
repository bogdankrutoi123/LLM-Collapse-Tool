import { useEffect, useState } from "react";
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

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

export default function Benchmark() {
  const [maxTokens, setMaxTokens] = useState("8000");
  const [topK, setTopK] = useState("20");
  const [rarePercentile, setRarePercentile] = useState("0.1");
  const [result, setResult] = useState<WikiTextBenchmark | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
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

  const handleRun = async () => {
    setError(null);
    setIsLoading(true);
    try {
      if (!selectedVersionId) {
        throw new Error("Select a model version to benchmark.");
      }
      const query = new URLSearchParams({
        model_version_id: selectedVersionId,
        dataset_id: datasetId,
        sample_count: sampleCount,
        max_new_tokens: maxNewTokens,
        temperature,
        num_beams: numBeams,
        max_tokens: maxTokens,
        top_k: topK,
        rare_percentile: rarePercentile
      });
      const data = await apiFetch<WikiTextBenchmark>(`/api/v1/analysis/wikitext/benchmark?${query}`);
      setResult(data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

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
  }, []);

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

  const handleUploadDataset = async () => {
    if (!datasetFile) {
      setError("Select a dataset file first.");
      return;
    }
    setError(null);
    setIsLoading(true);
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
      setIsLoading(false);
    }
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
          Evaluate a model version against a reference dataset to detect distribution shifts and collapse signals.
          The model generates continuations from sampled prompts, and the system computes entropy, perplexity,
          JS divergence, and vocabulary metrics compared to the reference corpus.
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
          <button className="button secondary" onClick={handleUploadDataset} disabled={isLoading}>
            Upload Dataset
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
        <button className="button" onClick={handleRun} disabled={isLoading}>
          {isLoading ? "Running..." : "Run Benchmark"}
        </button>
        <InsightCallout
          tone="info"
          title="Interpretation"
          text="Higher entropy generally implies richer token distribution, while higher JS divergence against reference may indicate instability or drift."
        />
        {error && <p className="small">{error}</p>}
      </div>

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
