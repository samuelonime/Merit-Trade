/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    serverComponentsExternalPackages: [],
  },
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
    
    // If no API URL is set, don't create the rewrite
    if (!apiUrl) {
      console.warn('NEXT_PUBLIC_API_URL is not set. API rewrites will be disabled.');
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