#!/usr/bin/env python3
"""Build validated per-service OPNsense IP feeds and separate domain feeds.

Only IP/CIDR values are written to dist/*.txt IP feeds. Domain names are
published under dist/domains/. DNS-derived addresses are explicitly marked
as volatile in the manifest because CDN/GeoDNS answers vary by resolver.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CONFIG = ROOT / "config" / "services.json"
USER_AGENT = "Serg434-OPNsense-Alias-Builder/2.0"
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_WORKERS = 16


class BuildError(RuntimeError):
    pass


def download(url: str, required: bool = True) -> str | None:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"}
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise BuildError(f"HTTP {response.status}: {url}")
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise BuildError(f"Download exceeds {MAX_DOWNLOAD_BYTES} bytes: {url}")
                return data.decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, OSError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    if required:
        raise BuildError(f"Required source unavailable: {url}: {last_error}")
    print(f"WARNING: optional source unavailable: {url}: {last_error}", file=sys.stderr)
    return None


def parse_ip_lines(content: str, family: int | None = None) -> tuple[set[str], int]:
    accepted: set[str] = set()
    rejected = 0
    for raw in content.splitlines():
        line = raw.strip().split("#", 1)[0].strip()
        if not line or line.startswith((";", "!")):
            continue
        # Support CIDR-only feeds and address feeds. Strip simple list syntax.
        line = line.removeprefix("address=").strip()
        try:
            if "/" in line:
                obj = ipaddress.ip_network(line, strict=False)
                if family and obj.version != family:
                    rejected += 1
                    continue
                if not obj.network_address.is_global or not obj.broadcast_address.is_global:
                    rejected += 1
                    continue
                value = obj.network_address.compressed if obj.prefixlen == obj.max_prefixlen else obj.with_prefixlen
            else:
                obj = ipaddress.ip_address(line)
                if family and obj.version != family:
                    rejected += 1
                    continue
                if not obj.is_global:
                    rejected += 1
                    continue
                value = obj.compressed
            accepted.add(value)
        except ValueError:
            rejected += 1
    return accepted, rejected


def parse_domains(lines: list[str]) -> list[str]:
    out = set()
    for raw in lines:
        domain = raw.strip().lower().rstrip(".")
        if not domain or domain.startswith(("#", ";", "!")):
            continue
        if domain.startswith("||"):
            domain = domain[2:].split("^", 1)[0]
        if domain.startswith("*."):
            domain = domain[2:]
        try:
            domain.encode("ascii")
            labels = domain.split(".")
            if len(labels) < 2 or len(domain) > 253:
                continue
            if all(1 <= len(x) <= 63 and x[0].isalnum() and x[-1].isalnum()
                   and all(c.isalnum() or c == "-" for c in x) for x in labels):
                out.add(domain)
        except UnicodeEncodeError:
            continue
    return sorted(out)


def resolve_domain(domain: str, timeout: float) -> tuple[str, set[str], str | None]:
    # getaddrinfo uses the runner resolver; avoid socket.setdefaulttimeout because it is process-global and unsafe across worker threads.
    try:
        answers = set()
        for item in socket.getaddrinfo(domain, None, type=socket.SOCK_STREAM):
            address = item[4][0].split("%", 1)[0]
            try:
                ip = ipaddress.ip_address(address)
                if ip.is_global:
                    answers.add(ip.compressed)
            except ValueError:
                pass
        return domain, answers, None if answers else "no global A/AAAA answers"
    except (socket.gaierror, OSError) as exc:
        return domain, set(), str(exc)



def sort_ips(values: set[str]) -> list[str]:
    def key(value: str):
        if "/" in value:
            net = ipaddress.ip_network(value, strict=False)
            return net.version, int(net.network_address), net.prefixlen
        ip = ipaddress.ip_address(value)
        return ip.version, int(ip), ip.max_prefixlen
    return sorted(values, key=key)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def main() -> int:
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        services = config["services"]
        if not services:
            raise BuildError("No services configured")
        timeout = float(config.get("dns_resolution", {}).get("timeout_seconds", 5))
        generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        service_results = {}
        all_v4: set[str] = set()
        all_v6: set[str] = set()
        all_domains: set[str] = set()
        total_dns_errors = 0

        # Fetch all configured source feeds before publishing anything.
        for service in services:
            sid = service["id"]
            domains = list(service.get("domains", []))
            source_meta = []
            ip_values: set[str] = set()
            rejected_by_source = {}
            for source in service.get("ip_sources", []):
                body = download(source["url"], required=source.get("required", True))
                if body is None:
                    continue
                entries, rejected = parse_ip_lines(body, source.get("family"))
                if not entries and source.get("required", True):
                    raise BuildError(f"{sid}: required IP source returned no usable entries: {source['url']}")
                ip_values.update(entries)
                rejected_by_source[source["url"]] = rejected
                source_meta.append({"url": source["url"], "accepted": len(entries), "rejected": rejected})
            for raw in service.get("static_ips", []):
                entries, rejected = parse_ip_lines(raw)
                if not entries or rejected:
                    raise BuildError(f"{sid}: invalid static IP/CIDR entry: {raw}")
                ip_values.update(entries)

            domain_source = service.get("domain_source")
            if domain_source:
                body = download(domain_source, required=True)
                domains.extend(parse_domains(body.splitlines()))
                source_meta.append({"url": domain_source, "type": "domains"})

            domains = parse_domains(domains)
            if not domains and not ip_values:
                raise BuildError(f"{sid}: no domains or IP ranges configured")
            service_results[sid] = {
                "category": service.get("category", "other"),
                "domains": domains,
                "ips": ip_values,
                "sources": source_meta,
                "rejected_by_source": rejected_by_source,
                "notes": service.get("notes", []),
                "dns_errors": [],
            }
            all_domains.update(domains)

        # Resolve domains in parallel; one failing hostname must not hide other
        # working endpoints. Per-service errors are exposed in the manifest.
        lookup = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(resolve_domain, d, timeout): d
                       for result in service_results.values() for d in result["domains"]}
            for future in as_completed(futures):
                domain, answers, error = future.result()
                lookup[domain] = answers
                if error:
                    total_dns_errors += 1

        for sid, result in service_results.items():
            for domain in result["domains"]:
                answers = lookup.get(domain, set())
                result["ips"].update(answers)
                if not answers:
                    result["dns_errors"].append(domain)
            ips = result["ips"]
            v4 = {x for x in ips if ipaddress.ip_address(x.split("/", 1)[0]).version == 4}
            v6 = ips - v4
            result["ipv4"] = sort_ips(v4)
            result["ipv6"] = sort_ips(v6)
            result["all"] = sort_ips(ips)
            all_v4.update(v4)
            all_v6.update(v6)

        # Existing YouTube feed remains the minimum safety baseline. Other
        # services can legitimately have only one address family or DNS data.
        youtube = service_results.get("youtube")
        if not youtube or len(youtube["ipv4"]) < 100 or len(youtube["ipv6"]) < 100:
            raise BuildError("YouTube baseline safety check failed (need >=100 IPv4 and >=100 IPv6 entries)")
        if len(all_v4) + len(all_v6) < 100:
            raise BuildError("Combined output unexpectedly small")

        # Stage every output in memory, then atomically replace individual files.
        outputs: dict[Path, str] = {}
        outputs[DIST / "all_ips.txt"] = "\n".join(sort_ips(all_v4 | all_v6)) + "\n"
        outputs[DIST / "all_ipv4.txt"] = "\n".join(sort_ips(all_v4)) + "\n"
        outputs[DIST / "all_ipv6.txt"] = "\n".join(sort_ips(all_v6)) + "\n"
        outputs[DIST / "all_domains.txt"] = "\n".join(sorted(all_domains)) + "\n"

        manifest_services = {}
        for sid, result in service_results.items():
            outputs[DIST / "ipv4" / f"{sid}.txt"] = "\n".join(result["ipv4"]) + ("\n" if result["ipv4"] else "")
            outputs[DIST / "ipv6" / f"{sid}.txt"] = "\n".join(result["ipv6"]) + ("\n" if result["ipv6"] else "")
            outputs[DIST / "domains" / f"{sid}.txt"] = "\n".join(result["domains"]) + "\n"
            manifest_services[sid] = {
                "category": result["category"],
                "counts": {"ipv4": len(result["ipv4"]), "ipv6": len(result["ipv6"]),
                           "ip_entries": len(result["all"]), "domains": len(result["domains"])},
                "sources": result["sources"],
                "rejected_by_source": result["rejected_by_source"],
                "dns_unresolved_domains": result["dns_errors"],
                "notes": result["notes"],
                "ip_resolution": "configured upstream/static prefixes plus GitHub Actions runner DNS A/AAAA answers; DNS results are resolver- and time-dependent",
            }

        # Thematic aggregate IP feeds; shared network ranges are deduplicated.
        categories = sorted({r["category"] for r in service_results.values()})
        for category in categories:
            ids = [sid for sid, r in service_results.items() if r["category"] == category]
            values = set().union(*(service_results[sid]["ips"] for sid in ids))
            outputs[DIST / f"{category}_all.txt"] = "\n".join(sort_ips(values)) + ("\n" if values else "")

        manifest = {
            "schema_version": 2,
            "generated_at": generated,
            "generator": "scripts/build_aliases.py",
            "dns_resolution": {"resolver": "GitHub Actions runner system resolver", "unresolved_domain_count": total_dns_errors,
                               "warning": "DNS-derived IPs can be GeoDNS/CDN answers and may change. They are not authoritative service-owned prefixes."},
            "counts": {"services": len(service_results), "ipv4_entries": len(all_v4),
                       "ipv6_entries": len(all_v6), "all_ip_entries": len(all_v4 | all_v6),
                       "domains": len(all_domains)},
            "services": manifest_services,
            "global_warnings": [
                "DNS-resolved addresses may be shared by unrelated services and can vary by resolver, geography and time.",
                "Meta IP ranges are shared across Facebook, Instagram, WhatsApp and Threads; service isolation is domain-based.",
                "No broad Google, Microsoft, AWS, Cloudflare or other cloud-provider ranges are imported.",
                "Domain feeds are separate from URL Table (IPs) feeds and must not be loaded as IP tables."
            ],
        }

        outputs[DIST / "manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

        # Remove legacy per-service combined IP feeds and the old nested aggregate
        # domain feed. Category aggregates and global all_ips.txt remain supported.
        legacy_paths = []
        for sid in service_results:
            legacy_paths.extend((DIST / f"{sid}.txt", DIST / f"{sid}_ipv4.txt", DIST / f"{sid}_ipv6.txt"))
        legacy_paths.append(DIST / "domains" / "all_domains.txt")

        for path, content in outputs.items():
            atomic_write(path, content)
        for path in legacy_paths:
            path.unlink(missing_ok=True)

        print(f"Build OK: services={len(service_results)}, IPv4={len(all_v4)}, IPv6={len(all_v6)}, "
              f"IP entries={len(all_v4 | all_v6)}, domains={len(all_domains)}, "
              f"unresolved domains={total_dns_errors}")
        for sid, result in service_results.items():
            print(f"  {sid}: v4={len(result['ipv4'])}, v6={len(result['ipv6'])}, "
                  f"domains={len(result['domains'])}, unresolved={len(result['dns_errors'])}")
        return 0
    except (BuildError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
