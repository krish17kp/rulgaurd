"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

// "/" (landing page) and "/lab/" (Streamlit) are other apps behind the same domain,
// so they get plain <a> links; everything else is a Next.js route.
const HOME = "/";
const LAB = "/lab/";

const PRIMARY_LINKS = [
  { href: "/upload", label: "Analyze" },
  { href: "/trajectory", label: "Trajectory" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/datasets", label: "Datasets" },
];

// Secondary/advanced routes - real, supported workflows, but not what a
// first-time visitor needs in the primary bar.
const MORE_LINKS = [
  { href: "/overview", label: "Overview" },
  { href: "/cross-dataset", label: "Cross-dataset" },
  { href: "/analyze-bearing-zip", label: "Analyze bearing ZIP" },
  { href: "/analyze-bundle", label: "Analysis Bundle" },
  { href: "/predict", label: "Predict (manual feature row)" },
  { href: "/degradation", label: "Degradation (manual feature rows)" },
];

const ALL_LINKS = [...PRIMARY_LINKS, ...MORE_LINKS];

function pillClass(active: boolean): string {
  return `rounded-full px-3 py-1.5 text-sm font-semibold transition ${
    active ? "bg-foreground text-background" : "hover:bg-foreground hover:text-background"
  }`;
}

export function SiteNav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-10 px-3 pt-3 pb-2">
      <nav className="mx-auto flex max-w-6xl items-center gap-2 rounded-full border-2 border-surface-border bg-background/85 py-2 pr-2 pl-4 shadow-[3px_3px_0_0_var(--foreground)] backdrop-blur-md">
        <a href={HOME} className="mr-2 flex items-center gap-2 font-display text-base font-extrabold">
          <img src="/favicon.svg" alt="" className="size-7" />
          RULGuard
        </a>

        <div className="ml-auto hidden items-center gap-1 md:flex">
          {PRIMARY_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? "page" : undefined}
              className={pillClass(pathname === link.href)}
            >
              {link.label}
            </Link>
          ))}
          <div className="relative">
            <button
              type="button"
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              className={pillClass(MORE_LINKS.some((l) => l.href === pathname))}
            >
              More
            </button>
            {moreOpen && (
              <div className="absolute right-0 mt-3 flex w-72 flex-col gap-1 rounded-3xl border-2 border-surface-border bg-background p-2 shadow-[3px_3px_0_0_var(--foreground)]">
                {MORE_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setMoreOpen(false)}
                    className={`rounded-2xl px-3 py-2 text-sm font-semibold ${
                      pathname === link.href ? "bg-mint" : "hover:bg-mint"
                    }`}
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
          <a
            href={LAB}
            className="ml-1 rounded-full border-2 border-surface-border bg-magenta px-4 py-2 font-display text-xs font-bold"
          >
            Research lab
          </a>
        </div>

        <button
          type="button"
          onClick={() => setMobileOpen((v) => !v)}
          aria-expanded={mobileOpen}
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
          className="ml-auto rounded-full border-2 border-surface-border p-2 md:hidden"
        >
          <span className="sr-only">{mobileOpen ? "Close menu" : "Open menu"}</span>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
            <path
              d="M3 5h14M3 10h14M3 15h14"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </nav>

      {mobileOpen && (
        <div className="mx-auto mt-2 flex max-w-6xl flex-col rounded-3xl border-2 border-surface-border bg-background p-2 shadow-[3px_3px_0_0_var(--foreground)] md:hidden">
          <a href={HOME} className="rounded-2xl px-4 py-3 font-display text-sm font-bold hover:bg-mint">
            Home
          </a>
          {ALL_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              aria-current={pathname === link.href ? "page" : undefined}
              className={`rounded-2xl px-4 py-3 font-display text-sm font-bold ${
                pathname === link.href ? "bg-mint" : "hover:bg-mint"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <a href={LAB} className="rounded-2xl px-4 py-3 font-display text-sm font-bold hover:bg-magenta">
            Research lab
          </a>
        </div>
      )}
    </header>
  );
}
