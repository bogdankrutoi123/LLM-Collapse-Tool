type InsightTone = "info" | "warning" | "success";

type InsightCalloutProps = {
  tone?: InsightTone;
  title: string;
  text: string;
};

export default function InsightCallout({ tone = "info", title, text }: InsightCalloutProps) {
  return (
    <div className={`insight-callout insight-${tone}`}>
      <strong>{title}</strong>
      <p className="small">{text}</p>
    </div>
  );
}
