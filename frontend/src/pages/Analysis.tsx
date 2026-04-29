import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, apiDownload } from "../api/client";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Legend, CartesianGrid } from "recharts";
import html2canvas from "html2canvas";
import { AggregatedMetric, Model, ModelVersion, VersionComparison } from "../api/types";
import MetricComparisonTable from "../components/MetricComparisonTable";
import InsightCallout from "../components/InsightCallout";
import { formatMetric, isSignificantChange, prettyMetricName, toNumber, toPercentChange } from "../utils/metrics";

type TrendRow = {
  label: string;
  entropy: number | null;
  kl: number | null;
  js: number | null;
};

type ComparisonRow = {
  metric: string;
  version_1: number | null;
  version_2: number | null;
  delta: number | null;
  percent_change: number | null;
  highlight: boolean;
};

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function parseComparisonRows(comparison: VersionComparison | null): ComparisonRow[] {
  if (!comparison) {
    return [];
  }

  const rowsFromChanges: ComparisonRow[] = comparison.changes
    .map((item) => {
      const metric = typeof item.metric === "string" ? item.metric : null;
      if (!metric) {
        return null;
      }
      return {
        metric,
        version_1: toNumber(item.version_1),
        version_2: toNumber(item.version_2),
        delta: toNumber(item.delta),
        percent_change: toNumber(item.percent_change),
        highlight: Boolean(item.highlight),
      };
    })
    .filter((row): row is ComparisonRow => row !== null);

  if (rowsFromChanges.length > 0) {
    return rowsFromChanges;
  }

  const metricsComparison = comparison.metrics_comparison as {
    version_1?: Record<string, unknown>;
    version_2?: Record<string, unknown>;
  };

  const version1 = metricsComparison.version_1 ?? {};
  const version2 = metricsComparison.version_2 ?? {};
  const metricKeys = Array.from(new Set([...Object.keys(version1), ...Object.keys(version2)]));

  return metricKeys.map((metric) => {
    const a = toNumber(version1[metric]);
    const b = toNumber(version2[metric]);
    const delta = a !== null && b !== null ? b - a : null;
    const percentChange = toPercentChange(a, delta);
    const highlight = isSignificantChange(percentChange, delta);
    return {
      metric,
      version_1: a,
      version_2: b,
      delta,
      percent_change: percentChange,
      highlight,
    };
  });
}

export default function Analysis() {
  const chartRef = useRef<HTMLDivElement>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [compareVersions, setCompareVersions] = useState<ModelVersion[]>([]);
  const [versionA, setVersionA] = useState("");
  const [versionB, setVersionB] = useState("");
  const [comparison, setComparison] = useState<VersionComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelVersionId, setModelVersionId] = useState("");
  const [aggregatedRaw, setAggregatedRaw] = useState<AggregatedMetric[]>([]);
  const [windowDays, setWindowDays] = useState<"all" | "7" | "30">("all");
  const [showEntropy, setShowEntropy] = useState(true);
  const [showKl, setShowKl] = useState(true);
  const [showJs, setShowJs] = useState(true);
  const [isTrendLoading, setIsTrendLoading] = useState(false);
  const [isComparisonLoading, setIsComparisonLoading] = useState(false);

  useEffect(() => {
    apiFetch<Model[]>("/api/v1/models/")
      .then((data) => {
        setModels(data);
        if (data.length > 0) {
          const firstId = String(data[0].id);
          setSelectedModelId((prev) => prev || firstId);
        }
      })
      .catch((error: unknown) => setError(getErrorMessage(error)));
  }, []);

  useEffect(() => {
    setVersionA("");
    setVersionB("");
    setModelVersionId("");
    setComparison(null);
    if (!selectedModelId) {
      setCompareVersions([]);
      return;
    }
    apiFetch<ModelVersion[]>(`/api/v1/models/${selectedModelId}/versions`)
      .then((data) => {
        setCompareVersions(data);
        if (data.length > 0) {
          setVersionA(String(data[0].id));
          setVersionB(String(data[Math.min(1, data.length - 1)].id));
          setModelVersionId(String(data[0].id));
        }
      })
      .catch((error: unknown) => setError(getErrorMessage(error)));
  }, [selectedModelId]);

  const fetchAggregated = async () => {
    if (!modelVersionId) return;
    try {
      setIsTrendLoading(true);
      const data = await apiFetch<AggregatedMetric[]>(`/api/v1/analysis/aggregated?model_version_id=${modelVersionId}`);
      setAggregatedRaw(data);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsTrendLoading(false);
    }
  };

  useEffect(() => {
    fetchAggregated();
  }, [modelVersionId]);

  const handleCompare = async () => {
    setError(null);
    if (!versionA || !versionB) {
      setError("Select both versions to compare.");
      return;
    }
    if (versionA === versionB) {
      setError('Select two different versions of the same model.');
      return;
    }
    try {
      setIsComparisonLoading(true);
      const data = await apiFetch<VersionComparison>("/api/v1/analysis/compare", {
        method: "POST",
        body: JSON.stringify({
          version_id_1: Number(versionA),
          version_id_2: Number(versionB)
        })
      });
      setComparison(data);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsComparisonLoading(false);
    }
  };

  const exportReport = async (format: "json" | "csv") => {
    setError(null);
    if (!versionA || !versionB) {
      setError("Select both versions to export a report.");
      return;
    }
    try {
      const res = await apiDownload("/api/v1/analysis/report", {
        method: "POST",
        body: JSON.stringify({
          version_id_1: Number(versionA),
          version_id_2: Number(versionB),
          format,
        }),
      });
      const url = window.URL.createObjectURL(res);
      const link = document.createElement("a");
      link.href = url;
      link.download = `comparison_report.${format}`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const exportPng = async () => {
    setError(null);
    if (!chartRef.current) return;
    try {
      const canvas = await html2canvas(chartRef.current);
      const url = canvas.toDataURL("image/png");
      const link = document.createElement("a");
      link.href = url;
      link.download = "charts.png";
      link.click();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const comparisonRows = parseComparisonRows(comparison);
  const aggregated = useMemo<TrendRow[]>(() => {
    if (aggregatedRaw.length === 0) {
      return [];
    }

    const now = Date.now();
    const filtered = aggregatedRaw.filter((row) => {
      if (windowDays === "all") {
        return true;
      }
      const cutoffMs = Number(windowDays) * 24 * 60 * 60 * 1000;
      const rowTime = new Date(row.period_start).getTime();
      return now - rowTime <= cutoffMs;
    });

    return filtered.map((row) => {
      const benchmark = (row.metrics_data as { benchmark?: { js_divergence?: number | null } } | null | undefined)?.benchmark;
      const js = typeof benchmark?.js_divergence === "number" ? benchmark.js_divergence : null;
      return {
        label: new Date(row.period_start).toLocaleString(),
        entropy: row.avg_entropy ?? null,
        kl: row.avg_kl_divergence ?? null,
        js,
      };
    });
  }, [aggregatedRaw, windowDays]);

  const trendQuality = useMemo(() => {
    const points = aggregated.length;
    const missingEntropy = aggregated.filter((row) => row.entropy === null).length;
    const missingKl = aggregated.filter((row) => row.kl === null).length;
    const missingJs = aggregated.filter((row) => row.js === null).length;
    const warnings: string[] = [];

    if (points > 0 && points < 5) {
      warnings.push("Trend has less than 5 points, interpretation may be noisy.");
    }
    if (missingEntropy > 0) {
      warnings.push(`Entropy is missing in ${missingEntropy} points.`);
    }
    if (missingKl === points && points > 0) {
      warnings.push("No KL divergence data — only available from per-prompt metrics, not from benchmark snapshots.");
    } else if (missingKl > 0) {
      warnings.push(`KL divergence is missing in ${missingKl} points.`);
    }
    if (missingJs > 0 && missingJs < points) {
      warnings.push(`JS divergence is missing in ${missingJs} points.`);
    }

    return warnings;
  }, [aggregated]);

  return (
    <div className="grid">
      <div className="card">
        <h2>Version Comparison</h2>
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
            value={versionA}
            onChange={(event) => setVersionA(event.target.value)}
          >
            <option value="">Version A</option>
            {compareVersions.map((version) => (
              <option key={version.id} value={version.id}>
                {version.version} (#{version.id})
              </option>
            ))}
          </select>
          <select
            className="input"
            value={versionB}
            onChange={(event) => setVersionB(event.target.value)}
          >
            <option value="">Version B</option>
            {compareVersions.map((version) => (
              <option key={version.id} value={version.id}>
                {version.version} (#{version.id})
              </option>
            ))}
          </select>
          <button className="button" onClick={handleCompare}>Compare</button>
        </div>
        <div className="form-row">
          <button className="button secondary" onClick={() => exportReport("json")}>Export JSON</button>
          <button className="button secondary" onClick={() => exportReport("csv")}>Export CSV</button>
        </div>
        <InsightCallout
          tone="info"
          title="Interpretation"
          text="Positive delta means Version B is higher than Version A. Marked significant values exceed 10% relative change or 0.1 absolute delta."
        />
        {error && <p className="small">{error}</p>}
        {isComparisonLoading && <p className="small">Loading comparison...</p>}
        {!isComparisonLoading && comparisonRows.length > 0 && (
          <MetricComparisonTable rows={comparisonRows} formatMetric={formatMetric} prettyMetricName={prettyMetricName} />
        )}
        {!isComparisonLoading && comparison && comparisonRows.length === 0 && (
          <p className="small">No comparable numeric metrics found for selected versions.</p>
        )}
      </div>

      <div className="card" ref={chartRef}>
        <div className="topbar">
          <h3>Metrics Trend</h3>
          <button className="button secondary" onClick={exportPng}>Export PNG</button>
        </div>
        <div className="form-row">
          <select
            className="input"
            value={modelVersionId}
            onChange={(event) => setModelVersionId(event.target.value)}
          >
            <option value="">Select version</option>
            {compareVersions.map((version) => (
              <option key={version.id} value={version.id}>
                {version.version} (#{version.id})
              </option>
            ))}
          </select>
          <select className="input" value={windowDays} onChange={(event) => setWindowDays(event.target.value as "all" | "7" | "30") }>
            <option value="all">All time</option>
            <option value="30">Last 30 days</option>
            <option value="7">Last 7 days</option>
          </select>
          <label className="small" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={showEntropy} onChange={(event) => setShowEntropy(event.target.checked)} />
            Show Entropy
          </label>
          <label className="small" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={showKl} onChange={(event) => setShowKl(event.target.checked)} />
            Show KL
          </label>
          <label className="small" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={showJs} onChange={(event) => setShowJs(event.target.checked)} />
            Show JS
          </label>
        </div>
        {isTrendLoading && <p className="small">Loading trend data...</p>}
        {!isTrendLoading && aggregated.length === 0 && (
          <p className="small">No aggregated metrics yet. Run aggregation or benchmark first.</p>
        )}
        {!isTrendLoading && aggregated.length > 0 && (
          <>
            {trendQuality.length > 0 && (
              <InsightCallout
                tone="warning"
                title="Data Quality Warning"
                text={trendQuality.join(" ")}
              />
            )}
            {showEntropy && (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={aggregated}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                  <YAxis label={{ value: "Entropy", angle: -90, position: "insideLeft" }} />
                  <Tooltip formatter={(value: number | null) => formatMetric(value)} />
                  <Legend />
                  <Line type="monotone" dataKey="entropy" name="Entropy" stroke="#3b82f6" connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
            {showKl && (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={aggregated}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                  <YAxis label={{ value: "KL Divergence", angle: -90, position: "insideLeft" }} />
                  <Tooltip formatter={(value: number | null) => formatMetric(value)} />
                  <Legend />
                  <Bar dataKey="kl" name="KL Divergence" fill="#10b981" />
                </BarChart>
              </ResponsiveContainer>
            )}
            {showJs && (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={aggregated}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                  <YAxis label={{ value: "JS Divergence", angle: -90, position: "insideLeft" }} />
                  <Tooltip formatter={(value: number | null) => formatMetric(value)} />
                  <Legend />
                  <Bar dataKey="js" name="JS Divergence" fill="#f59e0b" />
                </BarChart>
              </ResponsiveContainer>
            )}
            {!showEntropy && !showKl && !showJs && <p className="small">Select at least one metric to display chart.</p>}
          </>
        )}
      </div>
    </div>
  );
}
