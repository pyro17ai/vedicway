#!/usr/bin/env bash
set -Eeuo pipefail

readonly DISPLAY_NUMBER=":99"
readonly PROFILE_DIR="/opt/vedicway-tiktok-agent/shared/runtime/tiktok/chromium-profile"
readonly VNC_PASSWORD_FILE="/opt/vedicway-tiktok-agent/shared/runtime/tiktok/login-vnc.pass"
readonly LOGIN_URL="https://www.tiktok.com/login?lang=ru-RU"

export DISPLAY="${DISPLAY_NUMBER}"
export HOME="/home/ubuntu"

child_pids=()

stop_children() {
  if ((${#child_pids[@]})); then
    kill "${child_pids[@]}" 2>/dev/null || true
    wait "${child_pids[@]}" 2>/dev/null || true
  fi
}
trap stop_children EXIT INT TERM

install -d -m 700 "${PROFILE_DIR}"
test -r "${VNC_PASSWORD_FILE}"

Xvfb "${DISPLAY_NUMBER}" -screen 0 1440x1000x24 -nolisten tcp -noreset &
child_pids+=("$!")

for _ in {1..50}; do
  if xdpyinfo -display "${DISPLAY_NUMBER}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done
xdpyinfo -display "${DISPLAY_NUMBER}" >/dev/null

fluxbox -rc /opt/vedicway-tiktok-agent/current/scripts/tiktok/vps/fluxbox-init >/dev/null 2>&1 &
child_pids+=("$!")

/usr/bin/google-chrome \
  --user-data-dir="${PROFILE_DIR}" \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --disable-gpu \
  --password-store=basic \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9223 \
  --window-size=1440,1000 \
  "${LOGIN_URL}" >/dev/null 2>&1 &
child_pids+=("$!")

x11vnc \
  -display "${DISPLAY_NUMBER}" \
  -rfbauth "${VNC_PASSWORD_FILE}" \
  -rfbport 5909 \
  -localhost \
  -forever \
  -shared \
  -noxdamage \
  -repeat >/dev/null 2>&1 &
child_pids+=("$!")

websockify --web=/usr/share/novnc 127.0.0.1:6089 127.0.0.1:5909 >/dev/null 2>&1 &
child_pids+=("$!")

wait -n "${child_pids[@]}"
