# Repo-local agents

Installed from `https://github.com/samarth1106/vedic-astrology-skill` at commit
`af093d6cb407740cabd1f3b4dc91b0dc25b78bd6`.

## Skills

- `skills/vedic-astrology`
- `skills/numerology`

The upstream README, license, notice, examples, and tests are kept under
`vendor/vedic-astrology-skill`.

## Python runtime

Use the local virtual environment:

```powershell
.\.agents\.venv\Scripts\python.exe
```

Installed runtime packages include `pyswisseph`, `pytz`, `fpdf2`, and `pytest`.
The environment uses CPython 3.11 because the machine's Python 3.14 requires a
local C++ compiler to build `pyswisseph`.

## Rectification smoke command

```powershell
cd .agents\skills\vedic-astrology\scripts
D:\CODEX_WORK\VedicWay\.agents\.venv\Scripts\python.exe rectify.py --date 1990-08-15 --approx-time 14:30 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --window 6 --step 3 --event 2015-06-20:marriage --event 2018-03-10:child --json
```
