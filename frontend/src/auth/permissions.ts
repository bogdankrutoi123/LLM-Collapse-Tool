import { User, AppRole } from "../api/types";

export function getUserRole(user: User | null): AppRole {
  const role = user?.role;
  if (role === "admin" || role === "model_engineer" || role === "operator") {
    return role;
  }
  return "operator";
}

export function canManageModels(user: User | null): boolean {
  const role = getUserRole(user);
  return role === "admin" || role === "model_engineer";
}

export function canViewRules(user: User | null): boolean {
  return getUserRole(user) === "admin";
}