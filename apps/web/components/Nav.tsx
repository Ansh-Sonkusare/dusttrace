"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Overview", icon: <><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></> },
  { href: "/forecast", label: "Forecast", icon: <><path d="M3 17l5-6 4 3 4-7 5 6" /><path d="M3 21h18" /></> },
  { href: "/inspect", label: "Inspect today", icon: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /></> },
  { href: "/cases", label: "Cases", icon: <><rect x="4" y="4" width="16" height="17" rx="2" /><path d="M9 4V2h6v2" /><path d="M8 11h8M8 15h5" /></> },
  { href: "/sites", label: "Sites", icon: <><path d="M4 21V9l6-4v16" /><path d="M10 21V11h10v10" /><path d="M3 21h18" /></> },
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
