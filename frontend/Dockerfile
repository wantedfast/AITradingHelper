FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
ARG INTERNAL_API_BASE=http://127.0.0.1:8600
ENV INTERNAL_API_BASE=${INTERNAL_API_BASE}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
LABEL com.aitrading.managed="true"
ENV NODE_ENV=production
ENV INTERNAL_API_BASE=${INTERNAL_API_BASE}
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["npm", "run", "start"]
