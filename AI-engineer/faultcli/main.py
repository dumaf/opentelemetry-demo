"""FaultCLI entrypoint."""
from __future__ import annotations

import signal
import time
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from eyes_core.config import FLAGD_CONFIG_PATH
from eyes_core.flagd_client import FlagdClient
from eyes_core.inventory import build_inventory, save_inventory
from .state import capture_baselines, get_baseline, record_control_event, list_control_events

app = typer.Typer(name="faultcli", help="Independent feature-flag control for the OpenTelemetry Demo.")
console = Console()

def _client() -> FlagdClient:
    return FlagdClient()

def _valid_flags() -> dict[str, dict]:
    inv = {f["flag_key"]: f for f in build_inventory()}
    return inv

@app.command()
def list():
    """List discovered faults."""
    inv = build_inventory()
    t = Table(title="Discovered faults")
    t.add_column("Flag")
    t.add_column("Variants")
    t.add_column("Default")
    t.add_column("Service")
    for f in inv:
        t.add_row(f["flag_key"], ", ".join(f["available_variants"]), str(f["configured_default"]), f["affected_service"])
    console.print(t)

@app.command()
def inspect(fault: str):
    """Inspect a flag definition."""
    inv = {f["flag_key"]: f for f in build_inventory()}
    if fault not in inv:
        console.print(f"[red]Unknown fault: {fault}[/red]")
        raise typer.Exit(1)
    f = inv[fault]
    console.print(f"[bold]{f['flag_key']}[/bold]")
    console.print(f"Description: {f['description']}")
    console.print(f"State: {f['state']}")
    console.print(f"Default: {f['configured_default']}")
    console.print(f"Variants: {f['available_variants']}")
    console.print(f"Variant values: {f['variant_values']}")
    console.print(f"Targeting: {f['targeting']}")
    console.print(f"Affected service: {f['affected_service']}")
    console.print(f"Expected symptoms: {f['expected_symptoms']}")
    console.print(f"Schedulable: {f['schedulable']}")

@app.command()
def status():
    """Report active flag states."""
    capture_baselines()
    client = _client()
    try:
        flags = client.get_flags()
    except Exception as e:
        console.print(f"[red]Cannot read flag state: {e}[/red]")
        console.print("State: UNKNOWN")
        raise typer.Exit(1)
    t = Table(title="Flag status")
    t.add_column("Flag")
    t.add_column("Current defaultVariant")
    t.add_column("Baseline")
    t.add_column("State")
    for key, f in flags.items():
        cur = f.get("defaultVariant")
        base = get_baseline(key)
        state = "active" if (base is not None and str(cur) != str(base)) else "inactive"
        if base is None:
            state = "unknown-baseline"
        t.add_row(key, str(cur), str(base), state)
    console.print(t)

@app.command()
def trigger(fault: str, variant: str = typer.Option(..., "--variant", "-v"), dry_run: bool = typer.Option(False, "--dry-run")):
    """Activate a supported fault variant."""
    inv = _valid_flags()
    if fault not in inv:
        console.print(f"[red]Unknown fault: {fault}[/red]")
        raise typer.Exit(1)
    variants = inv[fault]["available_variants"]
    if variant not in variants:
        console.print(f"[red]Invalid variant '{variant}'. Valid: {variants}[/red]")
        raise typer.Exit(1)
    client = _client()
    capture_baselines()
    if dry_run:
        console.print(f"[yellow]DRY RUN: would set {fault} -> {variant}[/yellow]")
        return
    try:
        prev, _ = client.set_variant(fault, variant)
    except Exception as e:
        record_control_event(fault, "trigger", None, variant, False, error=str(e))
        console.print(f"[red]Failed: {e}[/red]")
        raise typer.Exit(1)
    record_control_event(fault, "trigger", prev, variant, True)
    console.print(f"[green]Set {fault}: {prev} -> {variant}[/green]")

@app.command()
def reset(fault: Optional[str] = typer.Argument(None), all: bool = typer.Option(False, "--all")):
    """Restore a fault (or all) to baseline."""
    client = _client()
    capture_baselines()
    if all:
        flags = client.get_flags()
        n = 0
        for key in flags:
            base = get_baseline(key)
            if base is None:
                continue
            cur = flags[key].get("defaultVariant")
            if str(cur) == str(base):
                continue
            try:
                client.reset_flag(key, base)
                record_control_event(key, "reset", cur, base, True)
                n += 1
            except Exception as e:
                record_control_event(key, "reset", cur, base, False, error=str(e))
                console.print(f"[red]{key}: {e}[/red]")
        console.print(f"[green]Reset {n} flags to baseline.[/green]")
        return
    if fault is None:
        console.print("[red]Provide a fault or --all[/red]")
        raise typer.Exit(1)
    inv = _valid_flags()
    if fault not in inv:
        console.print(f"[red]Unknown fault: {fault}[/red]")
        raise typer.Exit(1)
    base = get_baseline(fault)
    if base is None:
        capture_baselines()
        base = get_baseline(fault)
    try:
        cur = client.get_flag(fault).get("defaultVariant")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    try:
        client.reset_flag(fault, base)
        record_control_event(fault, "reset", cur, base, True)
        console.print(f"[green]Reset {fault}: {cur} -> {base}[/green]")
    except Exception as e:
        record_control_event(fault, "reset", cur, base, False, error=str(e))
        console.print(f"[red]Failed: {e}[/red]")
        raise typer.Exit(1)

@app.command()
def run(fault: str, duration: int = typer.Option(30, "--duration", "-d"), variant: Optional[str] = typer.Option(None, "--variant", "-v")):
    """Activate a fault for a bounded duration then restore."""
    inv = _valid_flags()
    if fault not in inv:
        console.print(f"[red]Unknown fault: {fault}[/red]")
        raise typer.Exit(1)
    if variant is None:
        # pick first non-off variant
        vs = [v for v in inv[fault]["available_variants"] if v != "off"]
        if not vs:
            console.print("[red]No non-off variant available[/red]")
            raise typer.Exit(1)
        variant = vs[0]
    if variant not in inv[fault]["available_variants"]:
        console.print(f"[red]Invalid variant[/red]")
        raise typer.Exit(1)
    client = _client()
    capture_baselines()
    base = get_baseline(fault)
    prev = None
    try:
        prev, _ = client.set_variant(fault, variant)
        record_control_event(fault, "run-start", prev, variant, True)
        console.print(f"[green]Activated {fault}={variant} for {duration}s[/green]")
        # handle interruption
        interrupted = {"flag": False}
        def handler(signum, frame):
            interrupted["flag"] = True
        signal.signal(signal.SIGINT, handler)
        for _ in range(duration):
            if interrupted["flag"]:
                break
            time.sleep(1)
    finally:
        try:
            client.reset_flag(fault, base if base is not None else (prev if prev is not None else "off"))
            record_control_event(fault, "run-end", variant, base, True)
            console.print(f"[green]Restored {fault}[/green]")
        except Exception as e:
            record_control_event(fault, "run-end", variant, base, False, error=str(e))
            console.print(f"[red]Cleanup failed: {e}[/red]")

@app.command()
def history(limit: int = typer.Option(50, "--limit", "-n")):
    """Show fault-control actions."""
    rows = list_control_events(limit=limit)
    t = Table(title="Control history")
    t.add_column("Time")
    t.add_column("Fault")
    t.add_column("Action")
    t.add_column("From")
    t.add_column("To")
    t.add_column("OK")
    for r in rows:
        t.add_row(r["ts"], r["fault_key"], r["action"], str(r["variant_from"]), str(r["variant_to"]), "yes" if r["success"] else "no")
    console.print(t)

@app.command()
def doctor():
    """Check availability of demo services and backends."""
    import httpx
    from eyes_core.config import (FLAGD_UI_BASE, PROMETHEUS_BASE, JAEGER_BASE, OPENSEARCH_BASE, OTEL_COLLECTOR_HTTP)
    targets = {
        "flagd-ui": f"{FLAGD_UI_BASE}/api/read",
        "prometheus": f"{PROMETHEUS_BASE}/-/healthy",
        "jaeger": f"{JAEGER_BASE}/api/services",
        "opensearch": f"{OPENSEARCH_BASE}/",
        "otel-collector": f"{OTEL_COLLECTOR_HTTP}/",
    }
    for name, url in targets.items():
        try:
            r = httpx.get(url, timeout=5.0)
            console.print(f"{name}: {'OK' if r.status_code < 400 else 'HTTP '+str(r.status_code)} ({url})")
        except Exception as e:
            console.print(f"{name}: UNAVAILABLE ({e})")
    # flagd config exists?
    console.print(f"flagd config: {'exists' if FLAGD_CONFIG_PATH.exists() else 'MISSING'} ({FLAGD_CONFIG_PATH})")
    save_inventory()
    console.print(f"Inventory written to artifacts/fault_inventory.json")

if __name__ == "__main__":
    app()
