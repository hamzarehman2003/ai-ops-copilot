import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/components/ThemeProvider";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { UserProvider } from "@/components/UserProvider";
import "./globals.css";

// Sans for the interface, mono for numbers and IDs. The woff2 files are committed (IBM Plex,
// SIL OFL, from @fontsource 5.3.0) so builds never fetch from Google Fonts: that fetch fails
// on CI runners and offline.
const plexSans = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-latin-400-normal.woff2", weight: "400" },
    { path: "./fonts/ibm-plex-sans-latin-500-normal.woff2", weight: "500" },
    { path: "./fonts/ibm-plex-sans-latin-600-normal.woff2", weight: "600" },
  ],
  variable: "--font-plex-sans",
});
const plexMono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-latin-400-normal.woff2", weight: "400" },
    { path: "./fonts/ibm-plex-mono-latin-500-normal.woff2", weight: "500" },
  ],
  variable: "--font-plex-mono",
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
      className={`${plexSans.variable} ${plexMono.variable}`}
    >
      <body className="min-h-screen text-[14px]">
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
