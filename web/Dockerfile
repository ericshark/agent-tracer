# Stage 1 — build the SPA
FROM node:22-alpine AS build

WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
RUN npm run build

# Stage 2 — serve with nginx (static files + API reverse proxy)
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
