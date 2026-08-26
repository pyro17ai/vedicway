#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_ROOT="/opt/vedicway-tiktok-agent"
readonly CREDENTIALS_FILE="/etc/vedicway-tiktok-login.credentials"
readonly VNC_PASSWORD_FILE="${APP_ROOT}/shared/runtime/tiktok/login-vnc.pass"

test "$(id -u)" -eq 0

login_password="$(openssl rand -hex 16)"
credentials_temp="$(mktemp)"

cleanup_temps() {
  rm -f -- "${credentials_temp}"
}
trap cleanup_temps EXIT

printf 'LOGIN_URL=%s\nVNC_PASSWORD=%s\n' \
  "http://127.0.0.1:6089/vnc.html?autoconnect=true&resize=remote&path=websockify" \
  "${login_password}" >"${credentials_temp}"

install -d -m 700 -o ubuntu -g ubuntu "${APP_ROOT}/shared/runtime/tiktok/chromium-profile"
sudo -u ubuntu x11vnc -storepasswd "${login_password}" "${VNC_PASSWORD_FILE}" >/dev/null
chmod 600 "${VNC_PASSWORD_FILE}"
chown ubuntu:ubuntu "${VNC_PASSWORD_FILE}"

install -m 600 -o root -g root "${credentials_temp}" "${CREDENTIALS_FILE}"

chmod 755 "${APP_ROOT}/current/scripts/tiktok/vps/login-desktop.sh"
install -m 644 -o root -g root \
  "${APP_ROOT}/current/scripts/tiktok/vps/vedicway-tiktok-login.service" \
  /etc/systemd/system/vedicway-tiktok-login.service
systemctl daemon-reload
systemctl enable vedicway-tiktok-login.service
systemctl restart vedicway-tiktok-login.service

for _ in {1..50}; do
  if curl --silent --fail "http://127.0.0.1:6089/vnc.html" >/dev/null; then
    break
  fi
  sleep 0.2
done

systemctl is-active --quiet vedicway-tiktok-login.service
curl --silent --fail "http://127.0.0.1:6089/vnc.html" >/dev/null
cat "${CREDENTIALS_FILE}"
