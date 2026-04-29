import { ReactNode } from "react";

type ComparisonRow = {
  metric: string;
  version_1: number | null;
  version_2: number | null;
  delta: number | null;
  percent_change: number | null;
  highlight: boolean;
};

type MetricComparisonTableProps = {
  rows: ComparisonRow[];
  formatMetric: (value: number | null, digits?: number) => string;
  prettyMetricName: (name: string) => string;
  leftLabel?: string;
  rightLabel?: string;
};

export default function MetricComparisonTable({
  rows,
  formatMetric,
  prettyMetricName,
  leftLabel = "Version A",
  rightLabel = "Version B",
}: MetricComparisonTableProps) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Metric</th>
          <th>{leftLabel}</th>
          <th>{rightLabel}</th>
          <th>Delta</th>
          <th>% Change</th>
          <th>Significance</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const deltaClass = row.delta === null ? "" : row.delta > 0 ? "metric-positive" : row.delta < 0 ? "metric-negative" : "";
          const badge: ReactNode = row.highlight ? (
            <span className="badge badge-significant">Significant</span>
          ) : (
            <span className="badge">Normal</span>
          );

          return (
            <tr key={row.metric} className={row.highlight ? "row-significant" : ""}>
              <td>{prettyMetricName(row.metric)}</td>
              <td>{formatMetric(row.version_1)}</td>
              <td>{formatMetric(row.version_2)}</td>
              <td className={deltaClass}>{formatMetric(row.delta)}</td>
              <td className={deltaClass}>{row.percent_change === null ? "N/A" : `${row.percent_change.toFixed(2)}%`}</td>
              <td>{badge}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
