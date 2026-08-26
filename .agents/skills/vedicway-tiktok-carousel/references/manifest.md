# Manifest выпуска TikTok

Локальный Playwright runner принимает JSON версии 1. Все пути должны находиться внутри `runtime/tiktok`; относительные пути считаются от каталога manifest. Номер позиции и порядок массива совпадают.

```json
{
  "version": 1,
  "run_id": "20260822-sun-moon-asc",
  "account": "@vedicway7",
  "topic": "Солнце, Луна и Асцендент в натальной карте",
  "title": "Солнце, Луна и Асцендент: в чём разница",
  "description": "Описание и от трёх до пяти хештегов",
  "sources": [
    "https://example.org/source-one",
    "https://example.org/source-two"
  ],
  "image_generation": {
    "skill": "imagegen",
    "tool": "image_gen"
  },
  "slides": [
    {
      "position": 1,
      "path": "slides/01.webp",
      "sha256": "64 lowercase hex characters",
      "width": 1080,
      "height": 1440,
      "mime_type": "image/webp"
    }
  ]
}
```

Массив `slides` содержит ровно шесть разных файлов и шесть разных SHA-256. Каждый файл весит не больше 20 МБ. `sources` содержит не меньше двух разных HTTPS-адресов. Поля `image_generation` фиксируют обязательное происхождение визуалов через `$imagegen`; runner дополнительно сверяет формат, путь и хеш каждого файла.
