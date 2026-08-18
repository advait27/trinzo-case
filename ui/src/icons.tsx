/* Inline SVG icons (Lucide geometry, 1.75 stroke). Inline rather than an icon
   package because the page must be one self-contained file, and no emoji
   because emoji are not icons -- they render differently per platform and
   carry no accessible name. */

type P = { size?: number; className?: string };
const base = (size: number) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.75,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
  "aria-hidden": true, focusable: false,
});

export const ShieldCheck = ({ size = 18, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
    <path d="m9 12 2 2 4-4" />
  </svg>
);
export const AlertTriangle = ({ size = 16, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
    <path d="M12 9v4" /><path d="M12 17h.01" />
  </svg>
);
export const HelpCircle = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="10" />
    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><path d="M12 17h.01" />
  </svg>
);
export const Search = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}>
    <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
  </svg>
);
export const Chevron = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}><path d="m6 9 6 6 6-6" /></svg>
);
export const Check = ({ size = 14, className }: P) => (
  <svg {...base(size)} className={className}><path d="M20 6 9 17l-5-5" /></svg>
);
export const CheckCircle = ({ size = 26, className }: P) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" />
  </svg>
);
export const Download = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <path d="M7 10l5 5 5-5" /><path d="M12 15V3" />
  </svg>
);
export const Printer = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M6 9V3h12v6" />
    <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
    <rect x="6" y="14" width="12" height="8" rx="1" />
  </svg>
);
export const Sun = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
  </svg>
);
export const Moon = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9" />
  </svg>
);
export const FileDiff = ({ size = 17, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z" />
    <path d="M14 2v5h5" /><path d="M12 11v5" /><path d="M9.5 13.5h5" />
  </svg>
);
export const Upload = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <path d="M17 8l-5-5-5 5" />
    <path d="M12 3v12" />
  </svg>
);

export const Ban = ({ size = 15, className }: P) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="10" /><path d="m4.9 4.9 14.2 14.2" />
  </svg>
);
export const Minus = ({ size = 14, className }: P) => (
  <svg {...base(size)} className={className}><path d="M5 12h14" /></svg>
);
