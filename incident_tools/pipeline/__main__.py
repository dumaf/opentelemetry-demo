"""Analyze one completed Eyes execution record and prepare a gated Hands handoff."""

import argparse
import json
from pathlib import Path
import tomllib

from incident_tools.eyes.runtime import Router, load
from .workflow import analyze, watch_eyes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eyes-log", help="Analyze one Eyes checkpoint1_execution_log.json")
    parser.add_argument("--eyes-config", required=True, help="Eyes operator TOML with model route")
    parser.add_argument("--hands-config", required=True, help="Hands operator TOML")
    parser.add_argument("--output-dir", help="New directory for one Brain/handoff analysis")
    parser.add_argument("--watch", action="store_true", help="Run Eyes watch and analyze each completed export")
    parser.add_argument("--investigate", metavar="INCIDENT_ID", help="Investigate a queued/incomplete Eyes incident, then run Brain and the Hands handoff")
    parser.add_argument("--output-root", help="Directory for analyses created by --watch or --investigate")
    parser.add_argument("--polls", type=int, default=0, help="Eyes poll count in --watch mode; 0 runs until interrupted")
    args = parser.parse_args(argv)
    if args.watch or args.investigate:
        if ((args.watch and args.investigate) or args.eyes_log or args.output_dir or not args.output_root
                or args.polls < 0 or (args.investigate and args.polls)):
            parser.error("Choose --watch or --investigate with --output-root; --polls is only for --watch")
    elif not args.eyes_log or not args.output_dir or args.output_root:
        parser.error("One-shot mode requires --eyes-log and --output-dir")
    eyes_cfg, _, _, eyes_artifact_dir = load(args.eyes_config)
    hands_file = Path(args.hands_config).resolve()
    with hands_file.open("rb") as stream:
        hands_cfg = tomllib.load(stream)
    mode = hands_cfg.get("adapter", {}).get("mode")
    if mode not in ("mock", "http"):
        parser.error("Hands integration requires mock or designated HTTP Action API mode")
    hands_dir = Path(hands_cfg["data_dir"])
    if not hands_dir.is_absolute():
        hands_dir = hands_file.parent / hands_dir
    router = Router(eyes_cfg["models"])
    allowed_services = set(hands_cfg["safety"]["services"])
    if args.watch or args.investigate:
        return watch_eyes(args.eyes_config, eyes_artifact_dir, router, args.output_root,
                          hands_dir, allowed_services, args.polls, incident_id=args.investigate)
    result = analyze(args.eyes_log, router, args.output_dir, hands_dir, allowed_services)
    print(json.dumps(result, indent=2))
    return 0 if result["hands_status"] == "awaiting_human_approval" else 2


if __name__ == "__main__":
    raise SystemExit(main())
