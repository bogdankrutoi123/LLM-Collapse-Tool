import { apiFetch } from "./client";
import { User } from "./types";

export type AuthBootstrapStatus = {
  has_admin: boolean;
  public_registration_enabled: boolean;
  bootstrap_admin_available: boolean;
};

export async function loginUser(username: string, password: string): Promise<User> {
  return apiFetch<User>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function logoutUser(): Promise<void> {
  await apiFetch<null>("/api/v1/auth/logout", { method: "POST" });
}

export async function fetchCurrentUser(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me");
}

export async function registerUser(payload: {
  email: string;
  username: string;
  password: string;
  full_name?: string;
}) {
  return apiFetch<User>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function bootstrapAdmin(payload: {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  bootstrap_token: string;
}) {
  return apiFetch<User>("/api/v1/auth/bootstrap-admin", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getAuthBootstrapStatus() {
  return apiFetch<AuthBootstrapStatus>("/api/v1/auth/bootstrap-status");
}
