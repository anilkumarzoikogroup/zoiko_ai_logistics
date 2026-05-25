import { useToastStore } from "@/hooks/useToast";
import { CheckCircle2, XCircle, Info, X } from "lucide-react";
import { cn } from "@/utils/cn";

export function Toaster() {
  const { toasts, remove } = useToastStore();
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            "flex items-start gap-3 rounded-xl border px-4 py-3 shadow-lg pointer-events-auto",
            "animate-in slide-in-from-right-5 fade-in duration-200",
            t.variant === "success" && "border-emerald-200 bg-emerald-50",
            t.variant === "error"   && "border-red-200 bg-red-50",
            t.variant === "info"    && "border-blue-200 bg-blue-50",
          )}
        >
          {t.variant === "success" && <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0 mt-0.5" />}
          {t.variant === "error"   && <XCircle       className="h-4 w-4 text-red-600 flex-shrink-0 mt-0.5" />}
          {t.variant === "info"    && <Info           className="h-4 w-4 text-blue-600 flex-shrink-0 mt-0.5" />}
          <div className="flex-1 min-w-0">
            <p className={cn(
              "text-sm font-semibold",
              t.variant === "success" && "text-emerald-800",
              t.variant === "error"   && "text-red-800",
              t.variant === "info"    && "text-blue-800",
            )}>
              {t.title}
            </p>
            {t.description && (
              <p className="text-xs text-muted-foreground mt-0.5">{t.description}</p>
            )}
          </div>
          <button
            onClick={() => remove(t.id)}
            className="text-muted-foreground hover:text-foreground flex-shrink-0 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
