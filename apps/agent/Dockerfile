# syntax=docker.io/docker/dockerfile:1

FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY apps/agent/package.json ./apps/agent/
COPY apps/agent/package-lock.json ./apps/agent/

# Install dependencies
RUN cd apps/agent && npm ci

# Copy source files
COPY apps/agent ./apps/agent

# Build the agent
RUN cd apps/agent && npm run build

# Production image
FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY apps/agent/package.json ./apps/agent/
COPY apps/agent/package-lock.json ./apps/agent/

# Install production dependencies
RUN cd apps/agent && npm ci --production

# Copy built files
COPY --from=builder /app/apps/agent/.mastra/output ./apps/agent/dist

# Set environment variables
ENV NODE_ENV=production
ENV PORT=3001

# Start the application
CMD ["node", "apps/agent/dist/index.mjs"] 