import Link from "next/link";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/upload", label: "Upload" },
  { href: "/degradation", label: "Degradation" },
  { href: "/predict", label: "Predict" },
  { href: "/evaluation", label: "Reliability" },
];

export function SiteNav() {
  return (
    <nav className="mx-auto flex max-w-3xl flex-wrap gap-x-4 gap-y-1 px-6 pt-6 text-sm">
      {LINKS.map((link) => (
        <Link key={link.href} className="underline" href={link.href}>
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
