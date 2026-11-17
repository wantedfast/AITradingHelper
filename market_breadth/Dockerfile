FROM node:20-alpine

WORKDIR /app
LABEL com.aitrading.managed="true"

COPY proxy.mjs ./proxy.mjs
COPY seed-data ./seed-data
COPY breadth.mjs backtest.mjs dashboard.html ./runtime/

RUN mkdir -p /app/runtime/data

ENV NODE_ENV=production
ENV GATEWAY_PORT=3211
EXPOSE 3211

CMD ["node", "/app/proxy.mjs"]
