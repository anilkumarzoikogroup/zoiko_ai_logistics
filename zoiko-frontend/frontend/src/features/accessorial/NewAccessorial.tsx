import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { accessorialApi } from "@/api/zoiko";
import { PlusCircle, Trash2, ArrowLeft, AlertCircle } from "lucide-react";

const CHARGE_TYPES = [
  { value: "DETENTION", label: "Detention" },
  { value: "DEMURRAGE", label: "Demurrage" },
  { value: "LIFTGATE", label: "Liftgate" },
  { value: "RESIDENTIAL", label: "Residential" },
  { value: "FUEL_SURCHARGE", label: "Fuel Surcharge" },
  { value: "OTHER", label: "Other" },
];

interface ChargeLine {
  charge_type: string;
  billed_amount: string;
  contracted_cap: string;
  tariff_id: string;
  tariff_version: string;
}

const emptyLine = (): ChargeLine => ({
  charge_type: "DETENTION",
  billed_amount: "",
  contracted_cap: "",
  tariff_id: "",
  tariff_version: "",
});

export default function NewAccessorial() {
  const navigate = useNavigate();

  const [carrierId, setCarrierId] = useState("");
  const [invoiceReference, setInvoiceReference] = useState("");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [currency, setCurrency] = useState<"INR" | "USD">("INR");
  const [chargeLines, setChargeLines] = useState<ChargeLine[]>([emptyLine()]);
  const [noBreach, setNoBreach] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      accessorialApi.submit({
        carrier_id: carrierId,
        invoice_reference: invoiceReference,
        invoice_date: invoiceDate,
        currency,
        charge_lines: chargeLines.map((l) => ({
          charge_type: l.charge_type,
          billed_amount: parseFloat(l.billed_amount),
          contracted_cap: parseFloat(l.contracted_cap),
          tariff_id: l.tariff_id || undefined,
          tariff_version: l.tariff_version || undefined,
        })),
      }),
    onSuccess: (result: any) => {
      if (result?.breach_detected === false) {
        setNoBreach(true);
        return;
      }
      const id = result?.case_id ?? result?.id;
      if (id) {
        navigate(`/accessorial/${id}`);
      }
    },
  });

  const updateLine = (idx: number, field: keyof ChargeLine, value: string) => {
    setChargeLines((prev) =>
      prev.map((line, i) => (i === idx ? { ...line, [field]: value } : line))
    );
  };

  const addLine = () => setChargeLines((prev) => [...prev, emptyLine()]);

  const removeLine = (idx: number) =>
    setChargeLines((prev) => prev.filter((_, i) => i !== idx));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setNoBreach(false);
    mutation.mutate();
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#F7F8FA",
        padding: "2rem 1rem",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
        color: "#1A2233",
      }}
    >
      <div style={{ maxWidth: "42rem", margin: "0 auto" }}>
        {/* Back link */}
        <Link
          to="/accessorial"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.375rem",
            color: "#5A6478",
            textDecoration: "none",
            fontSize: "0.875rem",
            marginBottom: "1.25rem",
            transition: "color 0.15s",
          }}
          onMouseEnter={(e) =>
            ((e.currentTarget as HTMLAnchorElement).style.color = "#2563EB")
          }
          onMouseLeave={(e) =>
            ((e.currentTarget as HTMLAnchorElement).style.color = "#5A6478")
          }
        >
          <ArrowLeft size={15} />
          Accessorial Disputes
        </Link>

        {/* Card */}
        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #E2E6ED",
            borderRadius: "0.5rem",
            padding: "2rem",
          }}
        >
          {/* Header */}
          <div style={{ marginBottom: "1.5rem" }}>
            <h1
              style={{
                fontSize: "1.25rem",
                fontWeight: 600,
                lineHeight: 1.3,
                margin: 0,
                color: "#1A2233",
              }}
            >
              Submit Accessorial Charge Dispute
            </h1>
          </div>

          {/* Info callout */}
          <div
            style={{
              borderLeft: "4px solid #3B82F6",
              background: "#EFF6FF",
              padding: "0.875rem 1rem",
              borderRadius: "0 0.375rem 0.375rem 0",
              marginBottom: "1.75rem",
              fontSize: "0.8125rem",
              color: "#1D4ED8",
              lineHeight: 1.55,
            }}
          >
            Each charge line is validated against your contracted tariff cap.
            Any excess triggers a governed dispute pipeline:{" "}
            <strong>
              Evidence → Reasoning → Proposal → Approval → Execution → ACR.
            </strong>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Base fields grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem 1.25rem",
                marginBottom: "1.5rem",
              }}
            >
              {/* Carrier ID */}
              <div style={{ gridColumn: "1 / -1" }}>
                <Label>Carrier ID</Label>
                <Input
                  type="text"
                  value={carrierId}
                  onChange={(e) => setCarrierId(e.target.value)}
                  placeholder="e.g. BLUEDART"
                  required
                />
              </div>

              {/* Invoice Reference */}
              <div>
                <Label>Invoice Reference</Label>
                <Input
                  type="text"
                  value={invoiceReference}
                  onChange={(e) => setInvoiceReference(e.target.value)}
                  placeholder="INV-2024-001"
                  required
                  style={{ fontFamily: "monospace" }}
                />
              </div>

              {/* Invoice Date */}
              <div>
                <Label>Invoice Date</Label>
                <Input
                  type="date"
                  value={invoiceDate}
                  onChange={(e) => setInvoiceDate(e.target.value)}
                  required
                />
              </div>

              {/* Currency */}
              <div>
                <Label>Currency</Label>
                <Select
                  value={currency}
                  onChange={(e) =>
                    setCurrency(e.target.value as "INR" | "USD")
                  }
                >
                  <option value="INR">INR — Indian Rupee</option>
                  <option value="USD">USD — US Dollar</option>
                </Select>
              </div>
            </div>

            {/* Charge Lines */}
            <div style={{ marginBottom: "1.5rem" }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "0.75rem",
                }}
              >
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    color: "#5A6478",
                  }}
                >
                  Charge Lines
                </span>
                <span
                  style={{
                    fontSize: "0.75rem",
                    color: "#5A6478",
                    background: "#F0F2F5",
                    borderRadius: "9999px",
                    padding: "0.125rem 0.625rem",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {chargeLines.length}
                </span>
              </div>

              <div
                style={{
                  border: "1px solid #E2E6ED",
                  borderRadius: "0.4rem",
                  overflow: "hidden",
                }}
              >
                {chargeLines.map((line, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "1rem",
                      borderBottom:
                        idx < chargeLines.length - 1
                          ? "1px solid #E2E6ED"
                          : "none",
                      background: idx % 2 === 0 ? "#FFFFFF" : "#FAFBFC",
                    }}
                  >
                    {/* Row label */}
                    <div
                      style={{
                        fontSize: "0.6875rem",
                        fontWeight: 600,
                        letterSpacing: "0.07em",
                        textTransform: "uppercase",
                        color: "#9BA3B2",
                        marginBottom: "0.625rem",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      Line {idx + 1}
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1.4fr 1fr 1fr",
                        gap: "0.75rem",
                        marginBottom: "0.75rem",
                      }}
                    >
                      <div>
                        <Label small>Charge Type</Label>
                        <Select
                          value={line.charge_type}
                          onChange={(e) =>
                            updateLine(idx, "charge_type", e.target.value)
                          }
                        >
                          {CHARGE_TYPES.map((ct) => (
                            <option key={ct.value} value={ct.value}>
                              {ct.label}
                            </option>
                          ))}
                        </Select>
                      </div>
                      <div>
                        <Label small>Billed Amount</Label>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={line.billed_amount}
                          onChange={(e) =>
                            updateLine(idx, "billed_amount", e.target.value)
                          }
                          placeholder="0.00"
                          required
                          style={{ fontVariantNumeric: "tabular-nums" }}
                        />
                      </div>
                      <div>
                        <Label small>Contracted Cap</Label>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={line.contracted_cap}
                          onChange={(e) =>
                            updateLine(idx, "contracted_cap", e.target.value)
                          }
                          placeholder="0.00"
                          required
                          style={{ fontVariantNumeric: "tabular-nums" }}
                        />
                      </div>
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr auto",
                        gap: "0.75rem",
                        alignItems: "flex-end",
                      }}
                    >
                      <div>
                        <Label small>Tariff ID (optional)</Label>
                        <Input
                          type="text"
                          value={line.tariff_id}
                          onChange={(e) =>
                            updateLine(idx, "tariff_id", e.target.value)
                          }
                          placeholder="TAR-001"
                          style={{ fontFamily: "monospace" }}
                        />
                      </div>
                      <div>
                        <Label small>Tariff Version (optional)</Label>
                        <Input
                          type="text"
                          value={line.tariff_version}
                          onChange={(e) =>
                            updateLine(idx, "tariff_version", e.target.value)
                          }
                          placeholder="v2.1"
                          style={{ fontFamily: "monospace" }}
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => removeLine(idx)}
                        disabled={chargeLines.length === 1}
                        title="Remove line"
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: "2rem",
                          height: "2rem",
                          border: "1px solid #E2E6ED",
                          borderRadius: "0.375rem",
                          background: "transparent",
                          color:
                            chargeLines.length === 1 ? "#CBD0D8" : "#DC2626",
                          cursor:
                            chargeLines.length === 1
                              ? "not-allowed"
                              : "pointer",
                          transition: "background 0.15s, border-color 0.15s",
                          padding: 0,
                          flexShrink: 0,
                          marginBottom: "1px",
                        }}
                        onMouseEnter={(e) => {
                          if (chargeLines.length > 1) {
                            (e.currentTarget as HTMLButtonElement).style.background =
                              "#FEF2F2";
                            (e.currentTarget as HTMLButtonElement).style.borderColor =
                              "#FCA5A5";
                          }
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.background =
                            "transparent";
                          (e.currentTarget as HTMLButtonElement).style.borderColor =
                            "#E2E6ED";
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}

                {/* Add line button */}
                <button
                  type="button"
                  onClick={addLine}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.375rem",
                    width: "100%",
                    padding: "0.75rem 1rem",
                    background: "#F7F8FA",
                    border: "none",
                    borderTop: "1px solid #E2E6ED",
                    color: "#2563EB",
                    fontSize: "0.8125rem",
                    fontWeight: 500,
                    cursor: "pointer",
                    transition: "background 0.15s",
                  }}
                  onMouseEnter={(e) =>
                    ((e.currentTarget as HTMLButtonElement).style.background =
                      "#EFF6FF")
                  }
                  onMouseLeave={(e) =>
                    ((e.currentTarget as HTMLButtonElement).style.background =
                      "#F7F8FA")
                  }
                >
                  <PlusCircle size={15} />
                  Add Charge Line
                </button>
              </div>
            </div>

            {/* No breach notice */}
            {noBreach && (
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.625rem",
                  background: "#F0FDF4",
                  border: "1px solid #86EFAC",
                  borderRadius: "0.375rem",
                  padding: "0.875rem 1rem",
                  marginBottom: "1.25rem",
                  fontSize: "0.875rem",
                  color: "#166534",
                }}
              >
                <AlertCircle size={16} style={{ marginTop: "1px", flexShrink: 0, color: "#16A34A" }} />
                <span>
                  No charges exceed contracted caps — no dispute pipeline was
                  triggered. Verify your billed amounts and contracted caps if
                  you expected a breach.
                </span>
              </div>
            )}

            {/* Mutation error */}
            {mutation.isError && (
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.625rem",
                  background: "#FEF2F2",
                  border: "1px solid #FCA5A5",
                  borderRadius: "0.375rem",
                  padding: "0.875rem 1rem",
                  marginBottom: "1.25rem",
                  fontSize: "0.875rem",
                  color: "#991B1B",
                }}
              >
                <AlertCircle size={16} style={{ marginTop: "1px", flexShrink: 0, color: "#DC2626" }} />
                <span>
                  {(mutation.error as any)?.message ||
                    "Submission failed. Check that all backends are running and try again."}
                </span>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={mutation.isPending}
              style={{
                width: "100%",
                padding: "0.75rem 1.25rem",
                background: mutation.isPending ? "#93C5FD" : "#2563EB",
                color: "#FFFFFF",
                border: "none",
                borderRadius: "0.4rem",
                fontSize: "0.9375rem",
                fontWeight: 600,
                cursor: mutation.isPending ? "not-allowed" : "pointer",
                transition: "background 0.15s",
                letterSpacing: "0.01em",
              }}
              onMouseEnter={(e) => {
                if (!mutation.isPending)
                  (e.currentTarget as HTMLButtonElement).style.background =
                    "#1D4ED8";
              }}
              onMouseLeave={(e) => {
                if (!mutation.isPending)
                  (e.currentTarget as HTMLButtonElement).style.background =
                    "#2563EB";
              }}
            >
              {mutation.isPending ? "Submitting…" : "Submit for Analysis"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

/* ─── Sub-components ──────────────────────────────────────────────────────── */

function Label({
  children,
  small,
}: {
  children: React.ReactNode;
  small?: boolean;
}) {
  return (
    <label
      style={{
        display: "block",
        fontSize: small ? "0.6875rem" : "0.75rem",
        fontWeight: 600,
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        color: "#5A6478",
        marginBottom: "0.3rem",
      }}
    >
      {children}
    </label>
  );
}

const inputBase: React.CSSProperties = {
  display: "block",
  width: "100%",
  padding: "0.5rem 0.625rem",
  fontSize: "0.875rem",
  color: "#1A2233",
  background: "#FFFFFF",
  border: "1px solid #D1D7E0",
  borderRadius: "0.375rem",
  outline: "none",
  boxSizing: "border-box",
  transition: "border-color 0.15s, box-shadow 0.15s",
};

function Input({
  style,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      style={{ ...inputBase, ...style }}
      onFocus={(e) => {
        (e.currentTarget as HTMLInputElement).style.borderColor = "#2563EB";
        (e.currentTarget as HTMLInputElement).style.boxShadow =
          "0 0 0 3px rgba(37,99,235,0.12)";
      }}
      onBlur={(e) => {
        (e.currentTarget as HTMLInputElement).style.borderColor = "#D1D7E0";
        (e.currentTarget as HTMLInputElement).style.boxShadow = "none";
      }}
    />
  );
}

function Select({
  style,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      style={{ ...inputBase, ...style, cursor: "pointer" }}
      onFocus={(e) => {
        (e.currentTarget as HTMLSelectElement).style.borderColor = "#2563EB";
        (e.currentTarget as HTMLSelectElement).style.boxShadow =
          "0 0 0 3px rgba(37,99,235,0.12)";
      }}
      onBlur={(e) => {
        (e.currentTarget as HTMLSelectElement).style.borderColor = "#D1D7E0";
        (e.currentTarget as HTMLSelectElement).style.boxShadow = "none";
      }}
    >
      {children}
    </select>
  );
}
