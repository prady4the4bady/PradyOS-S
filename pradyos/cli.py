"""PradyOS Sovereign CLI — stdlib-only HTTP client for a running instance.

Usage: python -m pradyos.cli [--url URL] <command> [args]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://localhost:8000"
TIMEOUT = 5.0


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _http_get(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read()
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def _http_post(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body if body is not None else {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        resp_body = resp.read()
    if not resp_body:
        return {}
    return json.loads(resp_body.decode("utf-8"))


def _table(rows: list[list[str]], headers: list[str]) -> str:
    all_rows = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]
    lines = []
    sep = "  "
    lines.append(sep.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    lines.append(sep.join("-" * widths[i] for i in range(len(headers))))
    for r in rows:
        lines.append(sep.join(str(r[i]).ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(lines)


# ── command functions ────────────────────────────────────────────────────────


def run_status(base_url: str) -> None:
    data = _http_get(f"{base_url}/api/v1/os/control")
    print(f"os_version:     {data.get('os_version', '?')}")
    print(f"uptime_seconds: {data.get('uptime_seconds', 0):.2f}")
    print()
    modules = data.get("modules", {})
    rows = []
    for name in sorted(modules.keys()):
        info = modules[name]
        present = "yes" if info.get("present") else "no"
        summary_keys = ",".join(sorted((info.get("summary") or {}).keys())) or "-"
        rows.append([name, present, summary_keys])
    print(_table(rows, ["module", "present", "summary_keys"]))


def run_tick(base_url: str) -> None:
    data = _http_post(f"{base_url}/api/v1/os/tick")
    print(f"ticks:     {len(data.get('ticks', []))}")
    print(f"healed:    {len(data.get('healed', []))}")
    print(f"reactions: {len(data.get('reactions', []))}")


def run_signals(base_url: str) -> None:
    data = _http_get(f"{base_url}/api/v1/signals")
    signals = data.get("signals", [])
    if not signals:
        print("(no signals)")
        return
    rows = [
        [s.get("name", "?"), str(s.get("count", 0)), str(s.get("latest", "-"))] for s in signals
    ]
    print(_table(rows, ["name", "count", "latest"]))


def run_signal_detail(base_url: str, name: str, limit: int = 100) -> None:
    url = f"{base_url}/api/v1/signals/{urllib.parse.quote(name)}?limit={limit}"
    data = _http_get(url)
    count = data.get("count", 0)
    stats = data.get("stats")
    print(f"signal: {data.get('name', name)}")
    print(f"count:  {count}")
    if stats:
        print(
            f"stats:  min={stats.get('min')} max={stats.get('max')} "
            f"mean={stats.get('mean')} stddev={stats.get('stddev')}"
        )
    else:
        print("stats:  (none)")
    points = data.get("points", [])
    if points:
        print(f"last {len(points)} points:")
        for p in points:
            print(f"  {p.get('recorded_at'):.3f}  {p.get('value')}")


def run_memory_get(base_url: str, key: str, namespace: str | None = None) -> None:
    url = f"{base_url}/api/v1/memory/{urllib.parse.quote(key)}"
    if namespace:
        url += f"?namespace={urllib.parse.quote(namespace)}"
    try:
        data = _http_get(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"not found: {key}")
            return
        raise
    print(f"key:   {data.get('key', key)}")
    print(f"value: {data.get('value', '-')}")
    print(f"tags:  {data.get('tags', [])}")
    ttl = data.get("ttl")
    print(f"ttl:   {ttl if ttl is not None else '(none)'}")


def run_memory_set(
    base_url: str,
    key: str,
    value: str,
    namespace: str | None = None,
    ttl: float | None = None,
) -> None:
    body: dict = {"value": value, "tags": []}
    if ttl is not None:
        body["ttl"] = ttl
    data = _http_post(f"{base_url}/api/v1/memory/{urllib.parse.quote(key)}", body)
    print(
        f"stored: {data.get('key', key)} = {data.get('value', value)} "
        f"(ttl={data.get('ttl', '-')})"
    )


def run_heartbeat(base_url: str) -> None:
    data = _http_get(f"{base_url}/api/v1/heartbeat/status")
    print(f"running:          {data.get('running', False)}")
    print(f"tick_count:       {data.get('tick_count', 0)}")
    print(f"interval_seconds: {data.get('interval_seconds', 0)}")


def run_health(base_url: str) -> None:
    try:
        data = _http_get(f"{base_url}/api/v1/health/score")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            data = _http_get(f"{base_url}/api/v1/health")
        else:
            raise
    score = data.get("score") if "score" in data else data.get("composite_score", "-")
    print(f"score: {score}")
    components = data.get("components") or data.get("breakdown") or []
    if components:
        print()
        if isinstance(components, list):
            rows = [[c.get("name", "?"), str(c.get("score", "-"))] for c in components]
            print(_table(rows, ["component", "score"]))
        else:
            for k, v in components.items():
                print(f"  {k}: {v}")


# ── arg parsing ──────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pradyos", description="PradyOS CLI")
    p.add_argument("--url", default=DEFAULT_URL, help="Base URL of PradyOS instance")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show OS status")
    sub.add_parser("tick", help="Trigger OS tick")
    sub.add_parser("signals", help="List signals")

    sig = sub.add_parser("signal", help="Show one signal's detail")
    sig.add_argument("name")
    sig.add_argument("--limit", type=int, default=100)

    mem = sub.add_parser("memory", help="Memory operations")
    mem_sub = mem.add_subparsers(dest="memory_op", required=True)
    mg = mem_sub.add_parser("get")
    mg.add_argument("key")
    mg.add_argument("--namespace")
    ms = mem_sub.add_parser("set")
    ms.add_argument("key")
    ms.add_argument("value")
    ms.add_argument("--namespace")
    ms.add_argument("--ttl", type=float)

    sub.add_parser("heartbeat", help="Show heartbeat status")
    sub.add_parser("health", help="Show health score")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    base = args.url

    try:
        if args.command == "status":
            run_status(base)
        elif args.command == "tick":
            run_tick(base)
        elif args.command == "signals":
            run_signals(base)
        elif args.command == "signal":
            run_signal_detail(base, args.name, args.limit)
        elif args.command == "memory":
            if args.memory_op == "get":
                run_memory_get(base, args.key, args.namespace)
            else:
                run_memory_set(base, args.key, args.value, args.namespace, args.ttl)
        elif args.command == "heartbeat":
            run_heartbeat(base)
        elif args.command == "health":
            run_health(base)
    except urllib.error.HTTPError as exc:
        print(f"Error: {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print(f"Error: could not connect to {base}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
