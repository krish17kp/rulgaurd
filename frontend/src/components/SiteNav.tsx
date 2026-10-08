"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const PRIMARY_LINKS = [
  { href: "/", label: "Overview" },
  { href: "/upload", label: "Analyze" },
  { href: "/trajectory", label: "Trajectory" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/datasets", label: "Datasets" },
];

// Secondary/advanced routes - real, supported workflows, but not what a
// first-time visitor needs in the primary bar (nightshift audit: the old
// navbar crammed 10 links across two font sizes and wrapped on anything
// narrower than a desktop).
const MORE_LINKS = [
  { href: "/cross-dataset", label: "Cross-dataset" },
  { href: "/analyze-bearing-zip", label: "Analyze bearing ZIP" },
  { href: "/analyze-bundle", label: "Analysis Bundle" },
  { href: "/predict", label: "Predict (manual feature row)" },
  { href: "/degradation", label: "Degradation (manual feature rows)" },
];

const ALL_LINKS = [...PRIMARY_LINKS, ...MORE_LINKS];

function linkClass(active: boolean): string {
  return active
    ? "font-medium text-accent"
    : "text-foreground-muted hover:text-foreground";
}

export function SiteNav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-10 border-b border-surface-border bg-background/90 backdrop-blur-sm">
      <nav className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-4 text-base">
        <Link href="/" className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <span className="inline-block size-2.5 rounded-full bg-accent" aria-hidden />
          RULGuard
        </Link>

        <div className="hidden items-center gap-6 md:flex">
          {PRIMARY_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? "page" : undefined}
              className={linkClass(pathname === link.href)}
            >
              {link.label}
            </Link>
          ))}
          <div className="relative">
            <button
              type="button"
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              className={linkClass(MORE_LINKS.some((l) => l.href === pathname))}
            >
              More
            </button>
            {moreOpen && (
              <div className="absolute right-0 mt-2 flex w-64 flex-col gap-1 rounded-lg border border-surface-border bg-surface p-2 shadow-lg">
                {MORE_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setMoreOpen(false)}
                    className={`rounded px-3 py-2 text-sm ${linkClass(pathname === link.href)}`}
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={() => setMobileOpen((v) => !v)}
          aria-expanded={mobileOpen}
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
          className="ml-auto rounded-lg border border-surface-border p-2 md:hidden"
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
        <div className="flex flex-col gap-1 border-t border-surface-border px-6 py-3 text-base md:hidden">
          {ALL_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              aria-current={pathname === link.href ? "page" : undefined}
              className={`rounded px-2 py-2 ${linkClass(pathname === link.href)}`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}
