import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency: string = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortHash(hash: string, chars: number = 8): string {
  if (!hash) return "—";
  const clean = hash.startsWith("0x") ? hash.slice(2) : hash;
  return `${clean.slice(0, chars)}…${clean.slice(-chars)}`;
}

export function generateIdempotencyKey(): string {
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
