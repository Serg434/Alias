#!/usr/bin/env python3
"""Build validated OPNsense feeds and a combined all-services IP list."""

from __future__ import annotations

import ipaddress
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
USER_AGENT = "Serg434-OPNsense-Alias-Builder/1.0"
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MIN_IPV4_ENTRIES = 100
MIN_IPV6_ENTRIES = 100

SOURCES = {
    "ipv4_hosts": (
        "https://raw.githubusercontent.com/touhidurrr/iplist-youtube/main/lists/ipv4.txt",
        4,
        "address",
    ),
    "ipv4_networks": (
        "https://raw.githubusercontent.com/touhidurrr/iplist-youtube/main/lists/cidr4.txt",
        4,
        "network",
    ),
    "ipv6_hosts": (
        "https://raw.githubusercontent.com/touhidurrr/iplist-youtube/main/lists/ipv6.txt",
        6,
        "address",
    ),
    "ipv6_networks": (
        "https://raw.githubusercontent.com/touhidurrr/iplist-youtube/main/lists/cidr6.txt",
        6,
        "network",
    ),
}

DOMAIN_SOURCE = (
    "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/youtube.lst"
)
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)


class BuildError(RuntimeError):
    pass


def download(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise BuildError(f"Download exceeds size limit: {url}")
                if response.status != 200:
                    raise BuildError(f"Unexpected HTTP status {response.status}: {url}")
                return data.decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise BuildError(f"Unable to download {url}: {last_error}")


def parse_feed(name: str, content: str, family: int, kind: str):
    accepted = set()
    rejected = 0
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "!")):
            continue
        try:
            if kind == "address":
                item = ipaddress.ip_address(line)
                if item.version != family or not item.is_global:
                    rejected += 1
                    continue
                normalized = item.compressed
            else:
                item = ipaddress.ip_network(line, strict=False)
                if item.version != family or not item.is_global:
                    rejected += 1
                    continue
                normalized = (
                    item.network_address.compressed
                    if item.prefixlen == item.max_prefixlen
                    else item.with_prefixlen
                )
            accepted.add(normalized)
        except ValueError:
            rejected += 1
    if not accepted:
        raise BuildError(f"Feed {name} produced no globally routable IPv{family} entries")
    return accepted, rejected


def parse_domains(content: str) -> list[str]:
    domains = set()
    rejected = 0
    for raw_line in content.splitlines():
        line = raw_line.strip().lower().rstrip(".")
        if not line or line.startswith(("#", ";", "!")):
            continue
        if line.startswith("||"):
            line = line[2:].split("^", 1)[0]
        if line.startswith("*."):
            line = line[2:]
        if DOMAIN_RE.fullmatch(line):
            domains.add(line)
        else:
            rejected += 1
    if len(domains) < 5:
        raise BuildError(
            f"Domain source unexpectedly small: {len(domains)} accepted, {rejected} rejected"
        )
    return sorted(domains)


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    try:
        parsed = {}
        rejected_by_source = {}
        source_counts = {}

        for name, (url, family, kind) in SOURCES.items():
            content = download(url)
            entries, rejected = parse_feed(name, content, family, kind)
            parsed[name] = entries
            rejected_by_source[name] = rejected
            source_counts[name] = len(entries)

        ipv4_set = parsed["ipv4_hosts"] | parsed["ipv4_networks"]
        ipv6_set = parsed["ipv6_hosts"] | parsed["ipv6_networks"]

        def ip_sort_key(value: str):
            network = ipaddress.ip_network(value, strict=False)
            return (network.version, int(network.network_address), network.prefixlen)

        ipv4 = sorted(ipv4_set, key=ip_sort_key)
        ipv6 = sorted(ipv6_set, key=ip_sort_key)
        all_ips = sorted(ipv4_set | ipv6_set, key=ip_sort_key)

        if len(ipv4) < MIN_IPV4_ENTRIES:
            raise BuildError(f"IPv4 output below safety threshold: {len(ipv4)}")
        if len(ipv6) < MIN_IPV6_ENTRIES:
            raise BuildError(f"IPv6 output below safety threshold: {len(ipv6)}")

        domains = parse_domains(download(DOMAIN_SOURCE))
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        manifest = {
            "schema_version": 1,
            "service": "youtube",
            "generated_at": generated_at,
            "counts": {
                "ipv4_entries": len(ipv4),
                "ipv6_entries": len(ipv6),
                "domains": len(domains),
                "all_ip_entries": len(all_ips),
            },
            "source_counts": source_counts,
            "rejected_entries": rejected_by_source,
            "sources": {
                **{name: value[0] for name, value in SOURCES.items()},
                "domains": DOMAIN_SOURCE,
            },
            "notes": [
                "Community-maintained upstream IP feeds; false positives are possible.",
                "Domain list is published separately and is not converted by resolving apex domains.",
                "Shared CDN/provider IPs may serve unrelated services.",
            ],
        }

        # Replace published files only after every source and safety check passes.
        write_atomic(DIST / "all_ips.txt", "\n".join(all_ips) + "\n")
        write_atomic(DIST / "youtube_ipv4.txt", "\n".join(ipv4) + "\n")
        write_atomic(DIST / "youtube_ipv6.txt", "\n".join(ipv6) + "\n")
        write_atomic(DIST / "youtube_domains.txt", "\n".join(domains) + "\n")
        write_atomic(
            DIST / "manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )

        print(
            f"Build OK: IPv4={len(ipv4)}, IPv6={len(ipv6)}, "
            f"domains={len(domains)}, all IPs={len(all_ips)}"
        )
        print(
            "Rejected entries by source: "
            + json.dumps(rejected_by_source, sort_keys=True)
        )
        return 0
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
