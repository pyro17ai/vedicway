# Release-only runtime inputs

Каталог исключён из Git. Перед production build положите сюда лицензированный `places.json` и Linux wheelhouse `pyjhora-mcp`.

Wheelhouse собирается в Linux-контейнере из зафиксированного commit исходников pyjhora-mcp. Он обязан содержать `pyjhora_mcp-0.1.0-*.whl`, все транзитивные wheels для CPython 3.11/Linux и `SHA256SUMS`. Backend image проверяет manifest и устанавливает пакеты с `--no-index`, поэтому build не подменит расчётные зависимости свежими версиями из PyPI.

Пример подготовки на Linux-хосте из каталога репозитория:

```sh
mkdir -p runtime/pyjhora-wheelhouse
docker run --rm \
  -v /absolute/path/to/pyjhora-mcp:/src:ro \
  -v "$PWD/runtime/pyjhora-wheelhouse:/wheelhouse" \
  python:3.11.13-slim-bookworm \
  sh -ec 'python -m pip install --no-cache-dir build && python -m pip wheel --wheel-dir /wheelhouse /src && cd /wheelhouse && sha256sum *.whl > SHA256SUMS'
```

Архивируйте wheelhouse вместе с commit SHA исходников и SHA256 manifest в release evidence. Wheelhouse, собранный на Windows, для Linux image не подходит.
