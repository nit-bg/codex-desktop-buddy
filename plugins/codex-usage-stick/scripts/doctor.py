#!/usr/bin/env python3
"""Diagnostics for the Codex Usage Stick plugin on Codex Desktop."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parents[1]
CODEX_HOME = Path.home() / ".codex"
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"


def plugin_version() -> str:
    try:
        data = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except Exception:
        return "unknown"
    return str(data.get("version") or "unknown")


def cache_hooks_path() -> Path:
    return (
        CODEX_HOME
        / "plugins"
        / "cache"
        / "codex-usage-stick-marketplace"
        / "codex-usage-stick"
        / plugin_version()
        / "hooks.json"
    )


def report(name: str, ok: bool, detail: str = "") -> bool:
    state = "ok" if ok else "fail"
    suffix = f" - {detail}" if detail else ""
    print(f"[{state}] {name}{suffix}")
    return ok


def check_json(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return report(str(path), True)
    except Exception as exc:
        return report(str(path), False, repr(exc))


def check_marketplace_json() -> bool:
    marketplace = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
    if marketplace.exists():
        return check_json(marketplace)
    cache_root = CODEX_HOME / "plugins" / "cache"
    if cache_root in PLUGIN_ROOT.parents:
        return report("marketplace json", True, "not present in installed plugin cache")
    return report(str(marketplace), False, "missing")


def check_python(paths: list[Path]) -> bool:
    ok = True
    for path in paths:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
            report(str(path), True)
        except Exception as exc:
            ok = False
            report(str(path), False, repr(exc))
    return ok


def check_bleak() -> bool:
    try:
        import bleak  # noqa: F401

        return report("Python bleak dependency", True)
    except ImportError:
        return report("Python bleak dependency", False, "install with: python -m pip install bleak")


def check_config() -> bool:
    config = CODEX_HOME / "config.toml"
    try:
        text = config.read_text(encoding="utf-8")
    except OSError as exc:
        return report(str(config), False, repr(exc))

    ok = True
    ok &= report("plugin_hooks enabled", "plugin_hooks = true" in text)
    ok &= report(
        "Codex Usage Stick plugin enabled",
        '[plugins."codex-usage-stick@codex-usage-stick-marketplace"]' in text
        and "enabled = true" in text,
    )
    if 'service_tier = "priority"' in text:
        report(
            "Codex service_tier",
            False,
            'this Codex CLI build expects "fast" or "flex"; app-server will log an error',
        )
    else:
        report("Codex service_tier", True)
    return ok


def check_cached_hooks() -> bool:
    source_hooks = PLUGIN_ROOT / "hooks.json"
    cache_hooks = cache_hooks_path()
    if not cache_hooks.exists():
        return report("installed hook cache", False, f"missing {cache_hooks}")
    try:
        source = json.loads(source_hooks.read_text(encoding="utf-8"))
        cached = json.loads(cache_hooks.read_text(encoding="utf-8"))
    except Exception as exc:
        return report("installed hook cache", False, repr(exc))

    source_text = json.dumps(source, sort_keys=True)
    cached_text = json.dumps(cached, sort_keys=True)
    ok = source_text == cached_text
    detail = "cache matches source" if ok else "cache differs from source; refresh/reinstall the plugin"
    return report("installed hook cache", ok, detail)


def check_windows_hook_bootstrap() -> bool:
    hooks_path = PLUGIN_ROOT / "hooks.json"
    try:
        hooks_config = json.loads(hooks_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return report("Windows hook bootstrap", False, repr(exc))

    problems: list[str] = []
    for event_name, matchers in hooks_config.get("hooks", {}).items():
        if not isinstance(matchers, list):
            continue
        for matcher_index, matcher in enumerate(matchers):
            for hook_index, hook in enumerate(matcher.get("hooks", [])):
                command = str(hook.get("commandWindows") or "")
                label = f"{event_name}:{matcher_index}:{hook_index}"
                if "$PLUGIN_ROOT" in command:
                    problems.append(f"{label} still uses $PLUGIN_ROOT")
                if "runpy.run_path" not in command or "codex-usage-stick" not in command:
                    problems.append(f"{label} does not use the cache bootstrap")

    detail = "uses cache bootstrap" if not problems else "; ".join(problems)
    return report("Windows hook bootstrap", not problems, detail)


def check_bridge_status() -> bool:
    script = PLUGIN_ROOT / "scripts" / "start_bridge.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--status"],
            cwd=str(PLUGIN_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return report("bridge status command", False, repr(exc))

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[-500:]
        return report("bridge status command", False, detail)
    try:
        status = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return report("bridge status command", False, proc.stdout.strip()[-500:])
    return report("bridge status command", True, f"state={status.get('state')} pid={status.get('pid')}")


async def scan_ble(timeout: float) -> bool:
    try:
        from bleak import BleakScanner
    except ImportError:
        return report("BLE scan", False, "missing bleak")

    devices = await BleakScanner.discover(timeout=timeout, service_uuids=[NUS_SERVICE_UUID])
    if not devices:
        devices = await BleakScanner.discover(timeout=timeout)
    interesting = [d for d in devices if "Codex" in (d.name or "") or "Claude" in (d.name or "")]
    if not interesting:
        names = ", ".join(sorted(d.name or d.address for d in devices[:12])) or "none"
        return report("BLE scan", False, f"no Codex device found; saw {names}")
    detail = ", ".join(f"{d.name or '-'} {d.address}" for d in interesting)
    return report("BLE scan", True, detail)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Codex Usage Stick plugin readiness.")
    parser.add_argument("--scan", action="store_true", help="Run a BLE scan for Codex devices")
    parser.add_argument("--scan-timeout", type=float, default=8.0)
    args = parser.parse_args()

    checks = [
        check_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json"),
        check_json(PLUGIN_ROOT / "hooks.json"),
        check_marketplace_json(),
        check_python([
            PLUGIN_ROOT / "scripts" / "start_bridge.py",
            PLUGIN_ROOT / "scripts" / "hook_entry.py",
            PLUGIN_ROOT / "scripts" / "codex_usage_ble_bridge.py",
        ]),
        check_bleak(),
        check_config(),
        check_windows_hook_bootstrap(),
        check_cached_hooks(),
        check_bridge_status(),
    ]
    if args.scan:
        checks.append(asyncio.run(scan_ble(args.scan_timeout)))

    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
