"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const PRIMARY_LINKS = [
  { href: "/", label: "Overview" },
  { href: "/upload", label: "Analyze" },
  { href: "/evaluation", label: "Reliability" },
  { href: "/trajectory", label: "Explore bearing trajectory" },
  { href: "/analyze-bearing-zip", label: "Analyze bearing ZIP" },
];

const ADVANCED_LINKS = [
  { href: "/predict", label: "Predict (manual feature row)" },
  { href: "/degradation", label: "Degradation (manual feature rows)" },
];

export function SiteNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-10 border-b border-surface-border bg-background/90 backdrop-blur-sm">
      <nav className="mx-auto flex max-w-3xl flex-wrap items-center gap-x-5 gap-y-2 px-6 py-3 text-sm">
        <Link href="/" className="mr-1 flex items-center gap-1.5 font-semibold tracking-tight">
          <span className="inline-block size-2 rounded-full bg-accent" aria-hidden />
          RULGuard
        </Link>
        {PRIMARY_LINKS.map((link) => {
          const active = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={
                active
                  ? "font-medium text-accent"
                  : "text-foreground-muted hover:text-foreground"
              }
            >
              {link.label}
            </Link>
          );
        })}
        <span className="ml-auto hidden text-xs text-foreground-muted/70 sm:inline">
          Advanced:
        </span>
        {ADVANCED_LINKS.map((link) => (
          <Link
            key={link.href}
            className={
              pathname === link.href
                ? "text-xs font-medium text-accent"
                : "text-xs text-foreground-muted/80 hover:text-foreground-muted"
            }
            href={link.href}
          >
            {link.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
