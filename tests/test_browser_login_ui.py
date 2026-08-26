from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_browser_login_runtime_is_private_and_persistent() -> None:
    compose = (ROOT / "compose.production.yml").read_text(encoding="utf-8")

    assert compose.count(
        'entrypoint: ["/usr/local/bin/vedicway-browser-login"]'
    ) == 2
    assert compose.count('VEDICWAY_BROWSER_HEADLESS: "0"') == 2
    assert compose.count("- vedicway_browser_vnc_password") == 2
    assert compose.count(
        "/tmp/.X11-unix:rw,nosuid,nodev,size=1m,uid=0,gid=0,mode=1777"
    ) == 2
    assert (
        '127.0.0.1:${VEDICWAY_DZEN_NOVNC_PORT:-6081}:6080' in compose
    )
    assert (
        '127.0.0.1:${VEDICWAY_PINTEREST_NOVNC_PORT:-6082}:6080' in compose
    )
    assert "${VEDICWAY_BROWSER_DATA_ROOT:-/var/lib/vedicway-browser}/dzen" in compose
    assert "${VEDICWAY_BROWSER_DATA_ROOT:-/var/lib/vedicway-browser}/pinterest" in compose
    assert "VEDICWAY_BROWSER_START_URL: https://ru.pinterest.com/login/" in compose
    assert "VEDICWAY_DZEN_CDP_URL: http://vedicway-seo-browser-dzen:9322" in compose
    assert (
        "VEDICWAY_PINTEREST_CDP_URL: http://vedicway-seo-browser-pinterest:9325"
        in compose
    )
    assert 'VEDICWAY_BROWSER_CDP_PROXY_PORT: "9322"' in compose
    assert 'VEDICWAY_BROWSER_CDP_PROXY_PORT: "9325"' in compose
    assert "9322:" not in compose
    assert "9325:" not in compose
    assert compose.count("netstat -ltn | grep -q '127.0.0.1:5900'") == 2
    assert compose.count("http://127.0.0.1:6080/vnc.html") == 2


def test_browser_login_entrypoint_keeps_display_and_vnc_off_public_networks() -> None:
    entrypoint = (
        ROOT / "seo_agent" / "browser_runtime" / "browser-login.sh"
    ).read_text(encoding="utf-8")

    assert "Xvfb" in entrypoint
    assert "-nolisten tcp" in entrypoint
    assert 'x_socket="/tmp/.X11-unix/X${display#:}"' in entrypoint
    assert 'kill -0 "$xvfb_pid"' in entrypoint
    assert "x11vnc" in entrypoint
    assert "-localhost" in entrypoint
    assert "-passwdfile /run/secrets/vedicway_browser_vnc_password" in entrypoint
    assert "websockify" in entrypoint
    assert "cdp-forward.mjs" in entrypoint
    assert 'flock -n 9' in entrypoint
    assert 'SingletonLock SingletonCookie SingletonSocket' in entrypoint
    assert 'exec node /opt/vedicway/seo_agent/browser_runtime/cloak-profile.mjs' in entrypoint


def test_backend_image_contains_private_browser_desktop_runtime() -> None:
    dockerfile = (ROOT / "docker" / "browser" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "ARG BASE_IMAGE" in dockerfile
    assert "test -f /opt/vedicway/seo_agent/browser_runtime/cloak-profile.mjs" in dockerfile
    for package in ("openbox", "x11vnc", "novnc", "websockify"):
        assert package in dockerfile
    assert "command -v flock" in dockerfile
    assert "vedicway-browser-login" in dockerfile
    assert "COPY seo_agent/browser_runtime/cdp-forward.mjs" in dockerfile


def test_browser_services_allow_a_graceful_profile_shutdown() -> None:
    compose = (ROOT / "compose.production.yml").read_text(encoding="utf-8")
    services = yaml.safe_load(compose)["services"]

    for service in (
        "vedicway-seo-browser-dzen",
        "vedicway-seo-browser-pinterest",
    ):
        assert services[service]["stop_grace_period"] == "45s"
