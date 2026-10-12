"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Overview", icon: <><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></> },
  { href: "/forecast", label: "Forecast", icon: <><path d="M3 17l5-6 4 3 4-7 5 6" /><path d="M3 21h18" /></> },
  { href: "/inspect", label: "Inspect today", icon: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /></> },
  { href: "/officer", label: "Today's visits", icon: <><path d="M12 21s-6-5.3-6-10a6 6 0 0 1 12 0c0 4.7-6 10-6 10z" /><circle cx="12" cy="11" r="2" /></> },
  { href: "/cases", label: "Cases", icon: <><rect x="4" y="4" width="16" height="17" rx="2" /><path d="M9 4V2h6v2" /><path d="M8 11h8M8 15h5" /></> },
  { href: "/sites", label: "Sites", icon: <><path d="M4 21V9l6-4v16" /><path d="M10 21V11h10v10" /><path d="M3 21h18" /></> },
  { href: "/report", label: "Weekly report", icon: <><path d="M6 3h9l3 3v15H6z" /><path d="M9 10h6M9 14h6M9 18h4" /></> },
  { href: "/data", label: "Data check", icon: <><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6" /><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></> },
];

export default function Nav() {
  const path = usePathname();
  return (
    <>
      {ITEMS.map((it) => {
        const active = it.href === "/" ? path === "/" : path.startsWith(it.href);
        return (
          <Link key={it.href} href={it.href} className="nav" aria-current={active ? "page" : undefined}>
            <svg viewBox="0 0 24 24" aria-hidden="true">{it.icon}</svg>
            <span>{it.label}</span>
          </Link>
        );
      })}
    </>
  );
}
