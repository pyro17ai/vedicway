#!/bin/sh
set -eu

display="${VEDICWAY_BROWSER_DISPLAY:-:99}"
screen="${VEDICWAY_BROWSER_SCREEN:-1440x900x24}"
password_file=/run/secrets/vedicway_browser_vnc_password
profile_dir="${VEDICWAY_BROWSER_USER_DATA_DIR:-}"

if [ ! -s "$password_file" ]; then
  echo "Browser desktop password secret is missing" >&2
  exit 1
fi
if [ "$profile_dir" != /var/lib/vedicway/browser-profile ]; then
  echo "Browser profile directory is outside the dedicated mount" >&2
  exit 1
fi

mkdir -p "$profile_dir"
exec 9>"$profile_dir/.vedicway-browser.lock"
if ! flock -n 9; then
  echo "Browser profile is already owned by another container" >&2
  exit 1
fi
for singleton_name in SingletonLock SingletonCookie SingletonSocket; do
  rm -f -- "$profile_dir/$singleton_name"
done

export DISPLAY="$display"
export HOME=/tmp/browser-home
export XDG_CONFIG_HOME=/tmp/xdg-config
export XDG_CACHE_HOME=/tmp/xdg-cache
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"

Xvfb "$display" -screen 0 "$screen" -nolisten tcp -ac &
xvfb_pid=$!
x_socket="/tmp/.X11-unix/X${display#:}"
wait_step=0
while [ ! -S "$x_socket" ] && [ "$wait_step" -lt 50 ]; do
  if ! kill -0 "$xvfb_pid" 2>/dev/null; then
    echo "Xvfb stopped before creating its display socket" >&2
    exit 1
  fi
  wait_step=$((wait_step + 1))
  sleep 0.1
done
if [ ! -S "$x_socket" ]; then
  echo "Xvfb display socket was not ready in time" >&2
  exit 1
fi
openbox-session >/tmp/openbox.log 2>&1 &
x11vnc \
  -display "$display" \
  -localhost \
  -forever \
  -shared \
  -rfbport 5900 \
  -passwdfile /run/secrets/vedicway_browser_vnc_password \
  >/tmp/x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/websockify.log 2>&1 &
node /opt/vedicway/seo_agent/browser_runtime/cdp-forward.mjs >/tmp/cdp-forward.log 2>&1 &

exec node /opt/vedicway/seo_agent/browser_runtime/cloak-profile.mjs
