# Three stages. The runtime carries neither the toolchain nor the source, only
# the standalone output Next produces — a few megabytes instead of a few hundred.

FROM node:22-slim AS deps
WORKDIR /app
COPY package.json ./
# No lockfile committed yet, so this resolves fresh. Once the tree settles a
# lockfile goes in and this becomes `npm ci`, which is reproducible.
RUN npm install --no-audit --no-fund


FROM node:22-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build


FROM node:22-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=8080

# Never root. A compromised process should not be able to write to its own image.
RUN useradd --create-home --shell /usr/sbin/nologin trimbin

# `standalone` includes only the files actually reached at runtime, traced from
# the entry point. Copying node_modules wholesale would ship the build toolchain
# to production for nothing.
COPY --from=build --chown=trimbin:trimbin /app/.next/standalone ./
COPY --from=build --chown=trimbin:trimbin /app/.next/static ./.next/static

USER trimbin
EXPOSE 8080

CMD ["node", "server.js"]
