/**
 * ZoikoLogo — Professional app icon that switches between light and dark variants.
 *
 * Light mode  → white background, purple-to-blue gradient Z, purple dotted ring
 * Dark mode   → dark (#0d1117) background, cyan-to-blue gradient Z, blue dotted ring
 *
 * Matches the brand images provided:
 *   image-2 (light): white bg, purple dots, cyan-purple Z
 *   image-3 (dark):  dark bg,  blue dots,   cyan-blue Z
 */

interface ZoikoLogoProps {
  theme: "light" | "dark";
  /** Total outer size in px — both width and height */
  size?: number;
  /** Show text "ZOIKO AI" next to the icon */
  showText?: boolean;
  collapsed?: boolean;
}

/** Generate evenly spaced dots on a circle */
function circleDots(
  cx: number, cy: number, radius: number,
  count: number, dotR: number, color: string
) {
  return Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    const opacity = 0.3 + 0.7 * Math.abs(Math.sin((i / count) * Math.PI));
    return (
      <circle
        key={i}
        cx={x} cy={y} r={dotR}
        fill={color}
        opacity={opacity}
      />
    );
  });
}

export default function ZoikoLogo({ theme, size = 40, showText = false, collapsed = false }: ZoikoLogoProps) {
  const isDark = theme === "dark";

  // Colours based on theme
  const bgColor     = isDark ? "#0b0f1a" : "#ffffff";
  const dotColor    = isDark ? "#60a5fa" : "#8b5cf6";  // blue in dark, purple in light
  const gradTop     = isDark ? "#22d3ee" : "#22d3ee";  // cyan both modes
  const gradBottom  = isDark ? "#3b82f6" : "#7c3aed";  // blue dark, purple light
  const shadowColor = isDark ? "rgba(96,165,250,0.35)" : "rgba(139,92,246,0.25)";

  const id = `zl-${isDark ? "d" : "l"}`;

  return (
    <div className="flex items-center gap-2.5">
      {/* Icon */}
      <svg
        width={size} height={size}
        viewBox="0 0 100 100"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          borderRadius: "22%",
          boxShadow: `0 4px 18px ${shadowColor}`,
          flexShrink: 0,
        }}
      >
        <defs>
          <linearGradient id={`${id}-grad`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%"   stopColor={gradTop}    />
            <stop offset="100%" stopColor={gradBottom} />
          </linearGradient>
          <linearGradient id={`${id}-bg`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={isDark ? "#0d1424" : "#f8faff"} />
            <stop offset="100%" stopColor={bgColor} />
          </linearGradient>
        </defs>

        {/* Background */}
        <rect x="0" y="0" width="100" height="100" fill={`url(#${id}-bg)`} rx="22" />

        {/* Dotted ring */}
        {circleDots(50, 50, 42, 44, 2.1, dotColor)}

        {/* Z letterform — stylised with flat top/bottom bars + diagonal */}
        <g fill={`url(#${id}-grad)`}>
          {/* Top bar */}
          <rect x="27" y="26" width="46" height="9" rx="4" />
          {/* Diagonal band — polygon */}
          <polygon points="66,35 73,35 34,65 27,65" />
          {/* Bottom bar */}
          <rect x="27" y="65" width="46" height="9" rx="4" />
        </g>
      </svg>

      {/* Text — only when expanded */}
      {showText && !collapsed && (
        <div className="leading-tight">
          <p className={`font-extrabold text-[15px] tracking-tight ${isDark ? "text-white" : "text-zoiko-navy"}`}>
            Zoiko <span className={`font-black ${isDark ? "text-cyan-400" : "text-zoiko-blue"}`}>AI</span>
          </p>
          <p className={`text-[9px] uppercase tracking-[0.18em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>
            AI Logistics
          </p>
        </div>
      )}
    </div>
  );
}
