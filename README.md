# OPNsense Proxy Aliases

Автоматическая сборка IP/CIDR- и доменных списков для OPNsense. В репозитории собраны как новые сервисы, так и известные существующие направления из текущей конфигурации.

## Публикуемые IP feeds

Все URL ниже содержат **только IP-адреса/CIDR**, без доменных имён:

- Общий IPv4 + IPv6: https://raw.githubusercontent.com/Serg434/Alias/main/dist/all_ips.txt
- Общий IPv4: https://raw.githubusercontent.com/Serg434/Alias/main/dist/all_ipv4.txt
- Общий IPv6: https://raw.githubusercontent.com/Serg434/Alias/main/dist/all_ipv6.txt
- Манифест: https://raw.githubusercontent.com/Serg434/Alias/main/dist/manifest.json

Для каждого сервиса публикуются три файла: `dist/<service>.txt` (IPv4 + IPv6), `dist/<service>_ipv4.txt`, `dist/<service>_ipv6.txt`. Категориальные объединения имеют вид `dist/<category>_all.txt`.

## Публикуемые домены

Домены не смешиваются с IP feeds. Для них отдельный каталог:

- Все домены: https://raw.githubusercontent.com/Serg434/Alias/main/dist/domains/all_domains.txt
- Сервис: https://raw.githubusercontent.com/Serg434/Alias/main/dist/domains/<service>.txt

Доменные списки предназначены для Host(s)/других доменных механизмов OPNsense, а не для URL Table (IPs).

## Включённые сервисы

AI: OpenAI/ChatGPT, Claude, Gemini, Grok, Perplexity, Copilot.  
Дизайн: Canva, Figma.  
Продуктивность: Notion.  
Социальные сети: Meta (Facebook, Instagram, WhatsApp, Threads), TikTok, Pinterest, LinkedIn.  
Мессенджеры: Telegram.  
Медиа: YouTube, Netflix, Wattpad.  
Существующие утилиты/инфраструктура: Arduino, 2ip.io и погодные API (Open-Meteo, wttr.in, MET Norway), Torrents.

## Источники и ограничения

- YouTube: community IP feeds `touhidurrr/iplist-youtube` (IPv4/IPv6 hosts и CIDR) и домены `itdoginfo/allow-domains`.
- Meta: IPv4/IPv6 префиксы `lord-alfred/ipranges`. Это общие сети Meta, а не раздельные диапазоны Facebook/Instagram/WhatsApp/Threads.
- Telegram: CIDR feed Telegram Core.
- Claude: статические префиксы, опубликованные в community-maintained ipranges, плюс DNS A/AAAA для перечисленных доменов.
- Остальные сервисы: DNS A/AAAA для явного перечня доменов из `config/services.json`.

DNS-ответы получены с резолвера GitHub Actions runner. Они зависят от времени, географии, CDN и DNS-резолвера; это не гарантированные постоянные диапазоны сервиса. Для Google и Microsoft не импортируются широкие диапазоны провайдеров: Gemini/Copilot IP-адреса могут пересекаться с обычными Google/Microsoft API. Облачные и CDN-диапазоны целиком не добавляются.

У Meta один общий IP-набор намеренно: разделить эти приложения по IP надёжно нельзя. Домены по каждому сервису перечислены в общем Meta domain feed; отдельные IP-фиды Facebook/Instagram/WhatsApp/Threads будут представлены общим набором Meta, если понадобится отдельное имя алиаса.

## Валидация

- IP-адреса и сети разбираются стандартным Python `ipaddress`; приватные, зарезервированные и некорректные значения отбрасываются.
- YouTube остаётся обязательным safety baseline: сборка останавливается, если его IPv4 или IPv6 меньше 100 записей.
- Недоступный обязательный upstream feed останавливает сборку до публикации.
- Ошибки отдельных DNS-имён не останавливают весь выпуск; они перечисляются в `manifest.json`.
- Генератор не импортирует широкие диапазоны Google, Microsoft, AWS или Cloudflare.
- IP- и domain-фиды разнесены по разным каталогам.

Важно: генератор заменяет содержимое публикуемых файлов только после успешного сбора всех обязательных источников и проверки базовых порогов. Для полного совпадения с вашими вручную созданными Host(s) алиасами Arduino/Torrents/Wattpad и прочими сервисами их фактические записи всё равно понадобятся при последующей сверке — сейчас в сбор включён проверяемый базовый доменный набор по названию сервиса.

## Обновления

GitHub Actions запускает сборку ежедневно в 03:17 UTC, при push в main и вручную через Actions → Update aliases → Run workflow.

## Безопасное подключение в OPNsense

Сначала создайте новые тестовые URL Table (IPs) aliases и проверьте количество записей и маршрутизацию. Не заменяйте текущие рабочие алиасы до проверки. Общий IP-feed — агрегат всех включённых сервисов и может включать общие CDN/DNS адреса; для точечной маршрутизации используйте сервисный IP-feed или доменный alias там, где это поддерживается.
