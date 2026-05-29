# Stage 1: build
FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_API_URL=/ means all API calls go to the same origin (nginx proxies)
ARG NEXT_PUBLIC_API_URL=/
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# Stage 2: runtime (~150 MB vs ~1 GB with node_modules)
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# public/ is optional in Next.js — copy only if it exists
RUN mkdir -p ./public
COPY --from=builder /app/public/ ./public/

EXPOSE 3000

CMD ["node", "server.js"]
