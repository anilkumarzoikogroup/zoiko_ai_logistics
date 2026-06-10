import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const SYMBOL_TO_ISO: Record<string, string> = {
  "₹": "INR", "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₩": "KRW",
};

export function formatCurrency(amount: number, currency: string = "INR"): string {
  const code = SYMBOL_TO_ISO[currency] ?? (currency?.length === 3 ? currency : "INR");
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: code,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${code} ${amount.toLocaleString("en-IN")}`;
  }
}

const IST = "Asia/Kolkata";

export function formatDate(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleString("en-IN", {
    timeZone: IST,
    day:    "2-digit",
    month:  "short",
    year:   "numeric",
    hour:   "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export function formatTime(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleTimeString("en-IN", {
    timeZone: IST,
    hour:   "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export function formatDateOnly(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleDateString("en-IN", {
    timeZone: IST,
    day:   "numeric",
    month: "short",
    year:  "numeric",
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
