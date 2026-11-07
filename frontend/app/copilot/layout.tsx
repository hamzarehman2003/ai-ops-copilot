import type { Metadata } from "next";
import type { ReactNode } from "react";

// The page is a client component, so its tab title is set here ("%s · Ops Copilot").
export const metadata: Metadata = { title: "Copilot" };

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
