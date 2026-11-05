FROM oven/bun:1.4.4-slim
WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
RUN bun run build

ENV NODE_ENV=production
ENV PORT=3000
ENV DATABASE_PATH=/data/prins.db

# SQLite lives on a mounted volume, so it survives redeploys.
RUN mkdir -p /data && chown bun:bun /data
VOLUME /data
USER bun

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD bun -e "const r = await fetch('http://127.0.0.1:3000/api/health'); process.exit(r.ok ? 0 : 1)"

CMD ["bun", ".output/server/index.mjs"]
