import type { NextConfig } from "next";

// The browser always calls same-origin `/api/*`; Next proxies it to the FastAPI backend,
// so there is no CORS to configure. API_URL is read when the Next server starts.
const API_URL = (process.env.API_URL || "http://localhost:8001").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
