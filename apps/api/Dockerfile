FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
COPY apps/api/package*.json apps/api/
RUN npm install --legacy-peer-deps
COPY . .
RUN npx prisma generate --schema=apps/api/prisma/schema.prisma
RUN npx nx build api --prod

# Prune dev dependencies from node_modules to save space
RUN npm prune --omit=dev --legacy-peer-deps

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/apps/api/dist ./dist
# Only production node_modules are copied
COPY --from=builder /app/node_modules ./node_modules
COPY apps/api/prisma ./prisma
RUN npx prisma generate
EXPOSE 3000
CMD ["node", "dist/main.js"]
