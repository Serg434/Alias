# OPNsense Proxy Aliases

Automated, validated IP/CIDR feeds for OPNsense URL Table (IPs). The first target is YouTube.

## Published files

After the first successful GitHub Actions run:

- IPv4: `https://raw.githubusercontent.com/Serg434/Alias/main/dist/youtube_ipv4.txt`
- IPv6: `https://raw.githubusercontent.com/Serg434/Alias/main/dist/youtube_ipv6.txt`
- Domains: `https://raw.githubusercontent.com/Serg434/Alias/main/dist/youtube_domains.txt`
- Manifest: `https://raw.githubusercontent.com/Serg434/Alias/main/dist/manifest.json`

The IPv4 and IPv6 files are intended for separate OPNsense aliases of type **URL Table (IPs)**. The domains file is published separately; it is not itself an IP alias.

## Initial YouTube sources

The builder merges and validates:

- `touhidurrr/iplist-youtube`: IPv4 hosts, IPv4 CIDRs, IPv6 hosts, IPv6 CIDRs.
- `itdoginfo/allow-domains`: YouTube domain list.

These are community-maintained upstream sources. False positives and shared CDN/provider ranges are possible. An IP list cannot guarantee service-level isolation where infrastructure is shared.

## Validation and safety

- IPv4 and IPv6 are emitted separately.
- Entries are parsed with Python's standard `ipaddress` module.
- Malformed, wrong-family, non-global and duplicate entries are rejected.
- The build fails if an upstream source cannot be downloaded, a feed is empty, or output counts fall below safety thresholds.
- Published files are replaced only after every source and threshold passes.
- GitHub Actions commits generated files only after a successful build.

## Automatic updates

GitHub Actions runs daily and can be started manually from **Actions → Update aliases → Run workflow**.

## OPNsense configuration

After the first successful workflow run, create two aliases of type **URL Table (IPs)**:

| Alias name | URL |
|---|---|
| `PROXY_DOMAINS_youtube_ipv4_new` | `https://raw.githubusercontent.com/Serg434/Alias/main/dist/youtube_ipv4.txt` |
| `PROXY_DOMAINS_youtube_ipv6_new` | `https://raw.githubusercontent.com/Serg434/Alias/main/dist/youtube_ipv6.txt` |

Do not delete or replace existing aliases until the new feeds have populated and routing has been tested. Keep IPv6 policy consistent with IPv4 to prevent bypasses.

## Important distinction: domains vs IPs

A domain list such as `youtube.lst` is not equivalent to a complete IP list. Resolving only apex domains does not discover all dynamic video/CDN subdomains. This project therefore publishes the domain list separately and does not pretend that resolving a few root domains produces complete coverage.

## Local build

No third-party Python packages are required:

```bash
python scripts/build_aliases.py
```
