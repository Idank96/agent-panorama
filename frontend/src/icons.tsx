import type { CSSProperties, ReactNode } from "react";

export interface IconProps {
  size?: number;
  className?: string;
  style?: CSSProperties;
}

interface IcProps extends IconProps {
  d?: string;
  fill?: boolean;
  sw?: number;
  children?: ReactNode;
}

// Simple stroked line icons. 1.6 stroke, currentColor.
const Ic = ({
  d,
  size = 16,
  fill = false,
  sw = 1.6,
  className,
  style,
  children,
}: IcProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill={fill ? "currentColor" : "none"}
    stroke="currentColor"
    strokeWidth={sw}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={{ display: "block", flexShrink: 0, ...style }}
  >
    {d ? <path d={d} /> : children}
  </svg>
);

export const IconActivity = (p: IconProps) => (
  <Ic {...p} d="M3 12h4l2.5 7 5-16 2.5 9H21" />
);
export const IconAgents = (p: IconProps) => (
  <Ic {...p}>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
    <path d="M16 6.2a3 3 0 0 1 0 5.6" />
    <path d="M17.5 20a5 5 0 0 0-3-4.6" />
  </Ic>
);
export const IconReports = (p: IconProps) => (
  <Ic {...p}>
    <path d="M6 3h8l4 4v14H6z" />
    <path d="M14 3v4h4" />
    <path d="M9 13h6M9 17h6M9 9h2" />
  </Ic>
);
export const IconSettings = (p: IconProps) => (
  <Ic {...p}>
    <circle cx="12" cy="12" r="2.6" />
    <path d="M12 3.5v2M12 18.5v2M5.5 5.5l1.4 1.4M17.1 17.1l1.4 1.4M3.5 12h2M18.5 12h2M5.5 18.5l1.4-1.4M17.1 6.9l1.4-1.4" />
  </Ic>
);
export const IconSearch = (p: IconProps) => (
  <Ic {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M16 16l4 4" />
  </Ic>
);
export const IconCalendar = (p: IconProps) => (
  <Ic {...p}>
    <rect x="3.5" y="4.5" width="17" height="16" rx="2" />
    <path d="M3.5 9h17M8 3v3M16 3v3" />
  </Ic>
);
export const IconExport = (p: IconProps) => (
  <Ic {...p}>
    <path d="M12 15V4" />
    <path d="M8 8l4-4 4 4" />
    <path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
  </Ic>
);
export const IconChevron = (p: IconProps) => (
  <Ic {...p}>
    <path d="M9 6l6 6-6 6" />
  </Ic>
);
export const IconCheck = (p: IconProps) => (
  <Ic {...p} sw={2}>
    <path d="M5 12.5l4.5 4.5L19 7" />
  </Ic>
);
export const IconX = (p: IconProps) => (
  <Ic {...p} sw={2}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Ic>
);
export const IconClose = (p: IconProps) => (
  <Ic {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Ic>
);
export const IconBolt = (p: IconProps) => (
  <Ic {...p}>
    <path d="M13 3L5 13h6l-1 8 8-10h-6z" />
  </Ic>
);
export const IconShield = (p: IconProps) => (
  <Ic {...p}>
    <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
    <path d="M9 12l2 2 4-4" />
  </Ic>
);
export const IconClock = (p: IconProps) => (
  <Ic {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Ic>
);
export const IconAlert = (p: IconProps) => (
  <Ic {...p}>
    <path d="M12 4l9 16H3z" />
    <path d="M12 10v4M12 17.5v.01" />
  </Ic>
);
