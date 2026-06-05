# Codex Usage Stick Plugin

This local Codex plugin starts a BLE bridge that sends Codex usage data to a
StickS3 running the matching Codex Usage Stick firmware.

The plugin is local-first:

- It reads local Codex usage files.
- It starts one background bridge process.
- It sends compact usage packets over BLE.
- It writes diagnostics under `~/.codex/codex-usage-bridge/`.
- It does not send data to an external server.

## Hooks

The plugin registers:

```text
SessionStart
UserPromptSubmit
PermissionRequest
```

The hooks run:

```sh
python3 "$PLUGIN_ROOT/scripts/hook_entry.py"
```

Windows compatibility note: Codex Desktop for Windows should install hook
commands that invoke the same entry point with `python`:

```powershell
python "$PLUGIN_ROOT/scripts/hook_entry.py"
```

The startup hooks return quickly: `hook_entry.py` writes a log line and asks
`start_bridge.py` to start or reuse the background bridge. The
`PermissionRequest` hook is synchronous and waits briefly for A/B on the
StickS3 before falling back to Codex's normal approval UI.

## Install From Codex UI

Open:

```text
Settings -> Plugins -> Add plugin marketplace
```

Fill the dialog like this:

```text
Source:
openelab-commits/codex-desktop-buddy

Git ref:
main
```

If this lives in your own fork, use your fork's `owner/repo`.

## CLI Fallback

```bash
/Applications/Codex.app/Contents/Resources/codex plugin marketplace add openelab-commits/codex-desktop-buddy --ref main
```

Windows:

```powershell
& "$env:LOCALAPPDATA\OpenAI\Codex\bin\codex.exe" plugin marketplace add openelab-commits/codex-desktop-buddy --ref main
```

For local development:

```bash
/Applications/Codex.app/Contents/Resources/codex plugin marketplace add /path/to/codex-desktop-buddy
```

Windows local development:

```powershell
& "$env:LOCALAPPDATA\OpenAI\Codex\bin\codex.exe" plugin marketplace add C:\path\to\codex-desktop-buddy
```

## Enable Hooks

Enable plugin hooks:

```bash
/Applications/Codex.app/Contents/Resources/codex features enable plugin_hooks
```

Windows compatibility note:

```powershell
& "$env:LOCALAPPDATA\OpenAI\Codex\bin\codex.exe" features enable plugin_hooks
```

If needed, enable the plugin in `~/.codex/config.toml`:

```toml
[plugins."codex-usage-stick@codex-usage-stick-marketplace"]
enabled = true
```

Restart Codex after changing plugin settings. Approve the hook trust prompt
when Codex shows it.

## Dependency

```bash
python3 -m pip install bleak
```

Windows compatibility note:

```powershell
python -m pip install bleak
```

## Runtime Files

```text
~/.codex/codex-usage-bridge/config.json
~/.codex/codex-usage-bridge/hook.log
~/.codex/codex-usage-bridge/bridge.log
~/.codex/codex-usage-bridge/bridge.pid
~/.codex/codex-usage-bridge/approval.json
```

## Config

Default `config.json`:

```json
{
  "name": "Codex-",
  "address": null,
  "interval": 5.0,
  "scan_timeout": 8.0,
  "restart_delay": 5.0,
  "verbose": true,
  "no_approval_proxy": true
}
```

Use `address` if macOS BLE name caching makes name scanning unreliable.
`no_approval_proxy` only disables the older app-server proxy experiment.
StickS3 approve/deny uses the `PermissionRequest` hook plus the local
approval IPC bridge and works with this value set to `true`. On Windows the
approval IPC bridge uses `127.0.0.1` plus a random token recorded in
`approval.json`; on POSIX it uses a Unix socket.

## Commands

Check status:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --status
```

Windows compatibility note: use `python` if `python3` is not available.

```powershell
python plugins/codex-usage-stick/scripts/start_bridge.py --status
```

Start:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py
```

Stop:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --stop
```

Run in foreground:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --foreground
```

Manual hook test:

```bash
python3 plugins/codex-usage-stick/scripts/hook_entry.py --event ManualTest
```

Run diagnostics:

```bash
python plugins/codex-usage-stick/scripts/doctor.py
```

## Verify

Make sure Bluetooth is enabled on the computer.

For the first BLE pairing on a new computer, start with a foreground `busy`
test so macOS can show the pairing prompt:

```bash
python3 ~/.codex/plugins/cache/codex-usage-stick-marketplace/codex-usage-stick/<version>/scripts/codex_usage_ble_bridge.py --verbose --state busy
```

The StickS3 should show a pairing code. Enter that code on the computer to
finish the BLE pairing. Once the hardware starts showing usage information,
stop the foreground test with `Command-C` / `Ctrl-C`.

Windows compatibility note: the current Windows-friendly firmware uses an open
NUS BLE link, so it does not show a pairing code. Run the same foreground test
with `python` if `python3` is not available.

Then submit a Codex prompt in a project where the plugin hook is trusted:

```bash
tail -n 20 ~/.codex/codex-usage-bridge/hook.log
```

Expected:

```text
"event": "UserPromptSubmit"
```

Then check BLE packets:

```bash
tail -n 40 ~/.codex/codex-usage-bridge/bridge.log
```

Expected:

```text
sent {"state":"busy","tokens":...,"primary":...,"secondary":...}
```

## Approve / Deny

When Codex asks for a permission approval, the bridge forwards the prompt to
the StickS3 through a local `PermissionRequest` hook. Press A to allow or B to
deny. If the StickS3 is not connected or no button is pressed before timeout,
the hook returns no decision and Codex falls back to its normal local approval
flow.
