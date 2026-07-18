FROM node:22.17.0-alpine3.22@sha256:fc3e945f920b7e3000cd1af86c4ae406ec70c72f328b667baf0f3a8910d69eed AS build

ARG VITE_PUBLIC_ORIGIN=""
ARG VITE_YANDEX_METRIKA_ID=""
ENV VITE_PUBLIC_ORIGIN=${VITE_PUBLIC_ORIGIN} \
    VITE_YANDEX_METRIKA_ID=${VITE_YANDEX_METRIKA_ID}

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY index.html tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts ./
COPY public ./public
COPY scripts ./scripts
COPY src ./src

RUN npm run build \
    && node scripts/prerender-seo.mjs \
    && test -s dist/index.html \
    && test -s dist/guide/index.html \
    && test -s dist/robots.txt \
    && test -s dist/sitemap.xml

FROM nginx:1.28.0-alpine3.21@sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284 AS runtime

RUN rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /tmp/nginx/client_temp /tmp/nginx/proxy_temp /tmp/nginx/fastcgi_temp /tmp/nginx/uwsgi_temp /tmp/nginx/scgi_temp \
    && chown -R 101:101 /tmp/nginx /var/cache/nginx /var/run

COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=101:101 /build/dist /usr/share/nginx/html

USER 101:101
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=4 \
  CMD wget -q -T 2 -O /dev/null http://127.0.0.1:8080/healthz || exit 1

STOPSIGNAL SIGQUIT
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
