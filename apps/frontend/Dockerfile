FROM node:20-alpine AS builder
WORKDIR /app

# Copy root package/lock
COPY package*.json ./
# Copy workspace config and frontend package.json
COPY nx.json ./
COPY tsconfig.base.json ./
COPY apps/frontend/package*.json apps/frontend/

RUN npm install --legacy-peer-deps

# Copy full source
COPY . .

# Build production bundle
RUN npx nx build frontend --prod

# -------------------------
# Production Stage
# -------------------------
FROM nginx:alpine

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets from builder
COPY --from=builder /app/apps/frontend/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY apps/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173
CMD ["nginx", "-g", "daemon off;"]
