<?php

declare(strict_types=1);

ignore_user_abort(true);
set_time_limit(0);
ini_set('output_buffering', 'off');
ini_set('zlib.output_compression', '0');
while (ob_get_level() > 0) {
    ob_end_clean();
}

$uri = $_SERVER['REQUEST_URI'] ?? '/';
if (!str_starts_with($uri, '/') || str_contains($uri, "\r") || str_contains($uri, "\n")) {
    http_response_code(400);
    exit;
}

$method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');
$target = 'https://origin.vedicway.ru:80' . $uri;
$requestHeaders = [];
$forwardedHeaders = [
    'HTTP_ACCEPT' => 'Accept',
    'HTTP_ACCEPT_ENCODING' => 'Accept-Encoding',
    'HTTP_ACCEPT_LANGUAGE' => 'Accept-Language',
    'HTTP_COOKIE' => 'Cookie',
    'HTTP_IDEMPOTENCY_KEY' => 'Idempotency-Key',
    'HTTP_IF_NONE_MATCH' => 'If-None-Match',
    'HTTP_LAST_EVENT_ID' => 'Last-Event-ID',
    'HTTP_ORIGIN' => 'Origin',
    'HTTP_REFERER' => 'Referer',
    'HTTP_USER_AGENT' => 'User-Agent',
    'HTTP_X_CLIENT_VERSION' => 'X-Client-Version',
    'HTTP_X_CSRF_TOKEN' => 'X-CSRF-Token',
];

foreach ($forwardedHeaders as $serverKey => $headerName) {
    $value = $_SERVER[$serverKey] ?? '';
    if ($value !== '' && !str_contains($value, "\r") && !str_contains($value, "\n")) {
        $requestHeaders[] = $headerName . ': ' . $value;
    }
}

$contentType = $_SERVER['CONTENT_TYPE'] ?? '';
if ($contentType !== '') {
    $requestHeaders[] = 'Content-Type: ' . $contentType;
}

$clientIp = filter_var($_SERVER['REMOTE_ADDR'] ?? '', FILTER_VALIDATE_IP) ?: 'unknown';
$requestHeaders[] = 'X-Real-IP: ' . $clientIp;
$requestHeaders[] = 'X-Forwarded-For: ' . $clientIp;
$requestHeaders[] = 'X-Forwarded-Proto: https';
$requestHeaders[] = 'Via: VedicWay-Timeweb-Edge';

$hopByHop = [
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailer',
    'transfer-encoding',
    'upgrade',
];

$curl = curl_init($target);
curl_setopt_array($curl, [
    CURLOPT_CUSTOMREQUEST => $method,
    CURLOPT_HTTPHEADER => $requestHeaders,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_CONNECTTIMEOUT => 10,
    CURLOPT_TIMEOUT => str_ends_with(parse_url($uri, PHP_URL_PATH) ?: '', '/events') ? 3600 : 360,
    CURLOPT_NOSIGNAL => true,
    CURLOPT_SSL_VERIFYPEER => true,
    CURLOPT_SSL_VERIFYHOST => 2,
    CURLOPT_RESOLVE => ['origin.vedicway.ru:80:43.156.18.74'],
    CURLOPT_HEADERFUNCTION => static function ($handle, string $line) use ($hopByHop): int {
        $length = strlen($line);
        $trimmed = trim($line);
        if ($trimmed === '') {
            return $length;
        }
        if (preg_match('/^HTTP\/\S+\s+(\d{3})/', $trimmed, $matches) === 1) {
            http_response_code((int) $matches[1]);
            return $length;
        }
        $separator = strpos($line, ':');
        if ($separator === false) {
            return $length;
        }
        $name = trim(substr($line, 0, $separator));
        $value = trim(substr($line, $separator + 1));
        if ($name === '' || in_array(strtolower($name), $hopByHop, true)) {
            return $length;
        }
        if (strtolower($name) === 'location') {
            $value = str_replace(
                ['https://origin.vedicway.ru:80', 'https://origin.vedicway.ru'],
                'https://vedicway.ru',
                $value,
            );
        }
        header($name . ': ' . $value, false);
        return $length;
    },
    CURLOPT_WRITEFUNCTION => static function ($handle, string $chunk): int {
        echo $chunk;
        flush();
        return strlen($chunk);
    },
]);

if ($method === 'HEAD') {
    curl_setopt($curl, CURLOPT_NOBODY, true);
} elseif (!in_array($method, ['GET', 'OPTIONS'], true)) {
    curl_setopt($curl, CURLOPT_POSTFIELDS, file_get_contents('php://input'));
}

$ok = curl_exec($curl);
if ($ok === false && !headers_sent()) {
    http_response_code(502);
    header('Content-Type: text/plain; charset=utf-8');
    echo "Шлюз временно не может связаться с основным сервером.\n";
}
curl_close($curl);
