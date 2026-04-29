export type AppRole = "admin" | "model_engineer" | "operator";
export type ComparisonOperator = ">" | "<" | ">=" | "<=" | "==";
export type RuleOperator = "any" | "all";
export type NotificationStatus = "pending" | "acknowledged" | "in_progress" | "closed";

export type Model = {
  id: number;
  name: string;
  description?: string;
  source?: string;
  status: string;
  created_at: string;
};

export type ModelVersion = {
  id: number;
  model_id: number;
  version: string;
  description?: string;
  deployment_date: string;
  previous_version_id?: number | null;
  metadata?: {
    hf_model_id?: string;
  };
  weights_path?: string | null;
  is_current: boolean;
};

export type Prompt = {
  id: number;
  model_version_id: number;
  input_text: string;
  output_text?: string;
  output_length?: number;
  generation_time_ms?: number;
  cpu_time_ms?: number;
  gpu_time_ms?: number;
  submitted_at: string;
};

export type PromptMetric = {
  id: number;
  prompt_id: number;
  entropy?: number;
  kl_divergence?: number;
  js_divergence?: number;
  wasserstein_distance?: number;
  ngram_drift?: number;
  embedding_drift?: number;
  rare_token_percentage?: number;
  new_token_percentage?: number;
  median_length?: number;
  length_variance?: number;
  calculated_at: string;
};

export type Notification = {
  id: number;
  title: string;
  message: string;
  severity: string;
  status: string;
  created_at: string;
};

export type AlertThreshold = {
  id: number;
  name: string;
  metric_name: string;
  threshold_value: number;
  comparison_operator: ComparisonOperator;
  persistence_count: number;
  persistence_window_minutes: number;
  group_key?: string;
  require_all_in_group: boolean;
  is_active: boolean;
  description?: string;
  created_at?: string;
  updated_at?: string | null;
};

export type AlertThresholdCreate = {
  name: string;
  metric_name: string;
  threshold_value: number;
  comparison_operator: ComparisonOperator;
  persistence_count: number;
  persistence_window_minutes: number;
  group_key?: string;
  require_all_in_group: boolean;
  is_active: boolean;
  description?: string;
};

export type AlertThresholdUpdate = Partial<Omit<AlertThresholdCreate, "name" | "metric_name">>;

export type AlertRuleItem = {
  id?: number;
  rule_id?: number;
  metric_name: string;
  threshold_value: number;
  comparison_operator: ComparisonOperator;
  persistence_count: number;
  persistence_window_minutes: number;
};

export type AlertRule = {
  id: number;
  name: string;
  operator: RuleOperator;
  description?: string;
  is_active: boolean;
  items: AlertRuleItem[];
  created_at?: string;
  updated_at?: string | null;
};

export type AlertRuleCreate = {
  name: string;
  operator: RuleOperator;
  description?: string;
  is_active?: boolean;
  items: AlertRuleItem[];
};

export type AlertRuleUpdate = Partial<Pick<AlertRuleCreate, "name" | "operator" | "description" | "is_active">>;

export type AggregatedMetric = {
  id: number;
  model_version_id: number;
  period_start: string;
  period_end: string;
  total_prompts: number;
  avg_entropy?: number | null;
  avg_kl_divergence?: number | null;
  avg_generation_time?: number | null;
  avg_output_length?: number | null;
  anomaly_count: number;
  anomaly_percentage?: number | null;
  metrics_data?: Record<string, unknown> | null;
  calculated_at: string;
};

export type VersionComparison = {
  version_1: ModelVersion;
  version_2: ModelVersion;
  metrics_comparison: Record<string, unknown>;
  changes: Array<Record<string, unknown>>;
};

export type User = {
  id: number;
  email: string;
  username: string;
  full_name?: string | null;
  role: AppRole;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
};

export type UserCreatePayload = {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  role?: AppRole;
};

export type UserUpdatePayload = {
  email?: string;
  username?: string;
  full_name?: string;
  role?: AppRole;
  is_active?: boolean;
};

export type AuditLog = {
  id: number;
  user_id?: number;
  action: string;
  entity_type: string;
  entity_id?: number;
  old_value?: Record<string, unknown> | null;
  new_value?: Record<string, unknown> | null;
  ip_address?: string | null;
  user_agent?: string | null;
  timestamp: string;
};

export type PromptSet = {
  id: number;
  name: string;
  description?: string;
  source_filename?: string;
  created_by_id?: number;
  created_at: string;
  item_count: number;
};

export type EvaluationJob = {
  id: number;
  prompt_set_id: number;
  model_version_id: number;
  reference_version_id?: number | null;
  status: string;
  error_message?: string | null;
  generation_params?: Record<string, unknown> | null;
  store_full_token_probs: boolean;
  top_k_token_probs: number;
  total_prompts: number;
  processed_prompts: number;
  successful_prompts: number;
  failed_prompts: number;
  created_by_id?: number | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
};

export type EvaluationCompare = {
  job_id_1: number;
  job_id_2: number;
  metrics_job_1: Record<string, number | null>;
  metrics_job_2: Record<string, number | null>;
  deltas: Record<string, number | null>;
};
