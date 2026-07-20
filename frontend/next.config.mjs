const internalApiBase = process.env.INTERNAL_API_BASE || "http://127.0.0.1:8600";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: "/pay/:path*",
          destination: `${internalApiBase}/api/pay-assets-disabled`,
        },
        {
          source: "/api/:path*",
          destination: `${internalApiBase}/api/:path*`,
        },
      ],
      afterFiles: [],
      fallback: [],
    };
  },
};

export default nextConfig;
