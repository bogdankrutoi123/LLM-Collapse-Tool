import { apiFetch } from "./client";
import {
  AlertRule,
  AlertRuleCreate,
  AlertRuleItem,
  AlertRuleUpdate,
  AlertThreshold,
  AlertThresholdCreate,
  AlertThresholdUpdate,
  AuditLog,
  User,
  UserCreatePayload,
  UserUpdatePayload,
} from "./types";

export function listThresholds() {
  return apiFetch<AlertThreshold[]>("/api/v1/thresholds/");
}

export function createThreshold(payload: AlertThresholdCreate) {
  return apiFetch<AlertThreshold>("/api/v1/thresholds/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateThreshold(thresholdId: number, payload: AlertThresholdUpdate) {
  return apiFetch<AlertThreshold>(`/api/v1/thresholds/${thresholdId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteThreshold(thresholdId: number) {
  return apiFetch<void>(`/api/v1/thresholds/${thresholdId}`, { method: "DELETE" });
}

export function listRules() {
  return apiFetch<AlertRule[]>("/api/v1/rules/");
}

export function createRule(payload: AlertRuleCreate) {
  return apiFetch<AlertRule>("/api/v1/rules/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateRule(ruleId: number, payload: AlertRuleUpdate) {
  return apiFetch<AlertRule>(`/api/v1/rules/${ruleId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function replaceRuleItems(ruleId: number, items: AlertRuleItem[]) {
  return apiFetch<AlertRule>(`/api/v1/rules/${ruleId}/items`, {
    method: "PUT",
    body: JSON.stringify(items),
  });
}

export function deleteRule(ruleId: number) {
  return apiFetch<void>(`/api/v1/rules/${ruleId}`, { method: "DELETE" });
}

export function listUsers() {
  return apiFetch<User[]>("/api/v1/users/");
}

export function createUser(payload: UserCreatePayload) {
  return apiFetch<User>("/api/v1/users/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateUser(userId: number, payload: UserUpdatePayload) {
  return apiFetch<User>(`/api/v1/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteUser(userId: number) {
  return apiFetch<void>(`/api/v1/users/${userId}`, { method: "DELETE" });
}

export function listAuditLogs() {
  return apiFetch<AuditLog[]>("/api/v1/audit/");
}
