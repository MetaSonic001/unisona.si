import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: { position: "bottom-right" },
  images: { remotePatterns: [{ protocol: "https", hostname: "img.clerk.com" }] },
};

export default nextConfig;
