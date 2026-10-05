import Link from "next/link";

const PRIMARY_LINKS = [
  { href: "/", label: "Overview" },
  { href: "/upload", label: "Analyze" },
  { href: "/evaluation", label: "Reliability" },
];

const ADVANCED_LINKS = [
  { href: "/predict", label: "Predict (manual feature row)" },
  { href: "/degradation", label: "Degradation (manual feature rows)" },
];

export function SiteNav() {
  return (
    <nav className="mx-auto flex max-w-3xl flex-wrap items-baseline gap-x-4 gap-y-1 px-6 pt-6 text-sm">
      {PRIMARY_LINKS.map((link) => (
        <Link key={link.href} className="underline" href={link.href}>
          {link.label}
        </Link>
      ))}
      <span className="text-zinc-400 dark:text-zinc-600">Advanced:</span>
      {ADVANCED_LINKS.map((link) => (
        <Link
          key={link.href}
          className="text-xs text-zinc-500 underline dark:text-zinc-500"
          href={link.href}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
