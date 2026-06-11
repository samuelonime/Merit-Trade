/** @type {import('next').NextConfig} */
const apiUrl = process.env.NEXT_PUBLIC_API_URL;

const nextConfig = {
  output: 'standalone',
  experimental: {
    serverComponentsExternalPackages: [],
  },
  async rewrites() {
    if (!apiUrl) {
      return [];
    }

    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
