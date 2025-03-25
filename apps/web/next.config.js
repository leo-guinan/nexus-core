/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    // Enable if you need server actions
    serverActions: true,
  }
}

module.exports = nextConfig 