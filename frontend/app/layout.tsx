import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/components/ThemeProvider";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { UserProvider } from "@/components/UserProvider";
import "./globals.css";

// Geist (Vercel, SIL OFL, from the geist 1.7.0 npm package) for the interface, Geist Mono for
// numbers and IDs. The variable woff2 files are committed so builds never fetch from Google
// Fonts: that fetch fails on CI runners and offline.
const geistSans = localFont({
  src: "./fonts/geist-sans-variable.woff2",
  weight: "100 900",
  variable: "--font-geist-sans",
});
const geistMono = localFont({
  src: "./fonts/geist-mono-variable.woff2",
  weight: "100 900",
  variable: "--font-geist-mono",
});

export const metadata: Metadata = {
  title: { default: "Ops Copilot", template: "%s · Ops Copilot" },
  description: "Support copilot: cited answers, account context and approved ticket actions.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning // next-themes sets the theme class before React loads
      className={`${geistSans.variable} ${geistMono.variable}`}
    >
      <body className="min-h-screen text-ui-lg">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <TooltipProvider delayDuration={300}>
            <UserProvider>
              <AppShell>{children}</AppShell>
            </UserProvider>
            <Toaster position="bottom-right" />
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
