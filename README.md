# OPNsense Proxy Aliases

Automated, validated IP/CIDR feeds for OPNsense **URL Table (IPs)**. YouTube is the first integrated service; the architecture is intended to grow to additional services.

## Published files

Generated files are committed to the repository after every successful build:

- **All services, IPv4 + IPv6:** `https://raw.githubusercontent.com/Serg434/Alias/main/dist/all_ips.txt`
- YouTube IPv4: `https://raw.githubusercontent.com/Serg434/Alias/main/dist/youtube_ipv4.txt`
- YouTube IPv6: `https://raw.githubusercontent.com/Serg434/Alias/main/dist/youtube_ipv6.txt`
- YouTube domains (not an IP alias): `https://raw.githubusercontent.com/Serg434/Alias/main/dist/youtube_domains.txt`
- Build manifest: `https://raw.githubusercontent.com/Serg434/Alias/main/dist/manifest.json`

`all_ips.txt` is the single combined feed: it contains all validated IP addresses and CIDR networks from every IP service feed integrated into this project, across both address families. It is deduplicated and sorted. As new services are added, their validated IP entries will be included automatically.

The combined feed is for a single OPNsense **URL Table (IPs)** alias. Before using it in production, verify that the installed OPNsense version accepts mixed IPv4/IPv6 entries in one URL Table and that the resulting table is populated as expected. Separate family feeds remain available for split routing and troubleshooting.

## Initial YouTube sources

- `touhidurrr/iplist-youtube`: IPv4 hosts, IPv4 CIDRs, IPv6 hosts and IPv6 CIDRs.
- `itdoginfo/allow-domains`: YouTube domain list.

These are community-maintained sources. False positives and shared CDN/provider ranges are possible; an IP list cannot guarantee service-level isolation where infrastructure is shared.

## Validation and safety

- IPv4 and IPv6 are emitted separately and also combined into `all_ips.txt`.
- Entries are parsed with Python's standard `ipaddress` module; malformed, wrong-family, non-global and duplicate entries are rejected.
- Host addresses and full-length host CIDRs are normalized to avoid duplicate representations.
- The build fails if a source cannot be downloaded, a feed is empty, or output counts fall below safety thresholds.
- Output files are written only after every source and threshold passes.
- Generated feeds are intentionally versioned in Git so OPNsense can fetch stable raw URLs.

## Automatic updates

GitHub Actions runs daily and can be started manually from **Actions → Update aliases → Run workflow**.

## OPNsense rollout

For the future unified routing rule, create a new alias (do not overwrite the existing working aliases yet):

| Alias name | Type | URL |
|---|---|---|
| `PROXY_DOMAINS_ALL_new` | URL Table (IPs) | `https://raw.githubusercontent.com/Serg434/Alias/main/dist/all_ips.txt` |

Keep the current aliases as rollback/reserve until the new alias is populated and routing has been tested. Note that the current combined file only contains services actually integrated into the builder; at this stage that is YouTube IP data, not every service currently configured manually in your OPNsense.

## Domains are not IPs

The domain list is published separately. It is not converted into IPs by resolving only apex domains, because that would miss dynamic subdomains and CDN endpoints.

## Local build

No third-party Python packages are required:

```bash
python scripts/build_aliases.py
```
