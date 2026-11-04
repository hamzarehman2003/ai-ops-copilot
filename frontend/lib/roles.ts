import type { Role } from "./api";

/** UI hints only: the backend enforces every permission regardless of what we show. */
export const canUpload = (role?: Role) => role === "admin";
export const canDecide = (role?: Role) => role === "admin" || role === "agent";

export const DEFAULT_USER = "agent@tasklane.example";
