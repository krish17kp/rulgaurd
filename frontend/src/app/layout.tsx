import type { Metadata } from "next";
import { Onest, Unbounded } from "next/font/google";
import { SiteNav } from "@/components/SiteNav";
import "./globals.css";

// Same faces as the landing page (web/), so the whole site reads as one.
const onest = Onest({
  variable: "--font-body",
  subsets: ["latin"],
});

const unbounded = Unbounded({
  variable: "--font-display-face",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "RULGuard",
  description: "Bearing degradation and Remaining Useful Life estimation",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${onest.variable} ${unbounded.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <SiteNav />
        {children}
      </body>
    </html>
  );
}
