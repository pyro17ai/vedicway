# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
RUN test -f /opt/vedicway/seo_agent/browser_runtime/cloak-profile.mjs \
    && test -f /opt/vedicway/seo_agent/browser_runtime/cdp-forward.mjs \
    && command -v flock \
    && apt-get update \
    && apt-get install -y --no-install-recommends openbox x11vnc novnc websockify xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY seo_agent/browser_runtime/browser-login.sh /usr/local/bin/vedicway-browser-login
COPY seo_agent/browser_runtime/cdp-forward.mjs /opt/vedicway/seo_agent/browser_runtime/cdp-forward.mjs
RUN chmod 0555 /usr/local/bin/vedicway-browser-login \
    && chmod 0444 /opt/vedicway/seo_agent/browser_runtime/cdp-forward.mjs

USER 10001:10001
