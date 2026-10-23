FROM node:22-slim AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_OAUTH_CLIENT_ID="" NEXT_PUBLIC_TRIAL_PASS=""
RUN npm run build
FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=8080 HOSTNAME=0.0.0.0
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin trimbin
COPY --from=build --chown=10001:10001 /app/.next/standalone ./
COPY --from=build --chown=10001:10001 /app/.next/static ./.next/static
USER 10001:10001
CMD ["node", "server.js"]
