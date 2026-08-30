FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install && npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3001 HOSTNAME=0.0.0.0
RUN addgroup -S nexus && adduser -S nexus -G nexus
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nexus:nexus /app/.next/standalone ./
COPY --from=builder --chown=nexus:nexus /app/.next/static ./.next/static
USER nexus
EXPOSE 3001
CMD ["node", "server.js"]
