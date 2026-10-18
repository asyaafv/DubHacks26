"""CLI for the extraction pipeline.

Usage:
    python -m backend.extraction.cli shared/seed/emails/hollister_10_percent.eml
    python -m backend.extraction.cli --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from backend.extraction.pipeline import FALLBACKS_ACTIVE, parse_eml, run_pipeline

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_EMAILS_DIR = _REPO_ROOT / "shared" / "seed" / "emails"
_DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _run_one(eml_path: Path, verbose: bool = True):
    email = parse_eml(eml_path.read_bytes())
    result = run_pipeline(email, _DEMO_USER_ID)
    if verbose:
        print(f"=== {eml_path.name} ===")
        print(f"classification: {result.classification} "
              f"(confidence {result.classification_confidence:.2f})")
        if not result.rewards:
            print("rewards: none")
        for reward in result.rewards:
            print(reward.model_dump_json(indent=2))
        print("\nstage timings (ms):")
        for stage, ms in result.timings_ms.items():
            print(f"  {stage:<14} {ms:>8.3f}")
    return result


def _run_all():
    eml_files = sorted(_SEED_EMAILS_DIR.glob("*.eml"))
    if not eml_files:
        print(f"no .eml files found in {_SEED_EMAILS_DIR}", file=sys.stderr)
        return 1

    header = (
        f"{'email':<28} {'class':<8} {'#':>2} {'kind':<12} {'value':>7} "
        f"{'code':<12} {'expires':<12} {'status':<13} {'conf':>5} {'ms':>8}"
    )
    print(header)
    print("-" * len(header))
    for path in eml_files:
        result = _run_one(path, verbose=False)
        if result.rewards:
            for reward in result.rewards:
                expires = reward.expires_at.date().isoformat() if reward.expires_at else "-"
                print(
                    f"{path.name:<28} {result.classification:<8} "
                    f"{len(result.rewards):>2} {reward.kind.value:<12} "
                    f"{reward.value:>7} {reward.code or '-':<12} {expires:<12} "
                    f"{reward.status.value:<13} {reward.overall_confidence:>5.2f} "
                    f"{result.timings_ms['total_ms']:>8.3f}"
                )
        else:
            print(
                f"{path.name:<28} {result.classification:<8} {0:>2} {'-':<12} "
                f"{'-':>7} {'-':<12} {'-':<12} {'-':<13} {'-':>5} "
                f"{result.timings_ms['total_ms']:>8.3f}"
            )
    if FALLBACKS_ACTIVE:
        print(f"\n(built-in fallbacks active for: {', '.join(FALLBACKS_ACTIVE)})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.extraction.cli",
        description="Run the Lapse reward-extraction pipeline on .eml files.",
    )
    parser.add_argument("eml", nargs="?", help="Path to a .eml file")
    parser.add_argument("--all", action="store_true", help="Run every seed email and print a summary table")
    args = parser.parse_args(argv)

    if args.all:
        return _run_all()
    if not args.eml:
        parser.print_usage(sys.stderr)
        return 2
    eml_path = Path(args.eml)
    if not eml_path.exists():
        print(f"file not found: {eml_path}", file=sys.stderr)
        return 1
    _run_one(eml_path)
    if FALLBACKS_ACTIVE:
        print(f"\n(built-in fallbacks active for: {', '.join(FALLBACKS_ACTIVE)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
