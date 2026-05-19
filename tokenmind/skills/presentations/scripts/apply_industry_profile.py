#!/usr/bin/env python3
"""Apply a curated design-system preset matching one of the bundled
industry profiles. Thin wrapper over ``apply_design_system.py`` whose
job is to give the LLM a stable "first-pass restyle" per industry.

The narrative `profiles/<name>.md` files describe the *storytelling* and
*structural* conventions for each industry — read those before composing
slides. This script only applies the *visual* preset (fonts + colors +
background) for the matching profile.

Examples
--------

  # See what profiles are available
  python apply_industry_profile.py --list

  # Print the preset spec without modifying the deck
  python apply_industry_profile.py --profile finance-ir --dump

  # Apply the consumer-retail visual preset to a deck
  python apply_industry_profile.py /tmp/deck.pptx --profile consumer-retail

  # Apply, then override an individual key
  python apply_industry_profile.py /tmp/deck.pptx --profile engineering-platform \\
      --override accent_color=8B5CF6

Profiles
--------

  - consumer-retail       : warm, energetic, rose accent
  - engineering-platform  : clean technical, Inter, cyan accent
  - finance-ir            : conservative, navy + gold
  - gtm-growth            : punchy, emerald accent
  - product-platform      : minimal, blue accent
  - appendix-heavy        : muted, light-gray background
  - template-and-edit     : neutral starting point (Arial, gray)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


PROFILES: dict[str, dict[str, Any]] = {
    "consumer-retail": {
        "heading_font": "Helvetica Neue",
        "body_font":    "Helvetica Neue",
        "heading_color": "1F1F1F",
        "body_color":    "4A4A4A",
        "accent_color":  "E11D48",
        "slide_bg":      "FFFFFF",
    },
    "engineering-platform": {
        "heading_font": "Inter",
        "body_font":    "Inter",
        "heading_color": "0F172A",
        "body_color":    "475569",
        "accent_color":  "06B6D4",
        "slide_bg":      "FFFFFF",
    },
    "finance-ir": {
        "heading_font": "Georgia",
        "body_font":    "Helvetica Neue",
        "heading_color": "0B2545",
        "body_color":    "455A7A",
        "accent_color":  "C19A28",
        "slide_bg":      "FFFFFF",
    },
    "gtm-growth": {
        "heading_font": "Inter",
        "body_font":    "Inter",
        "heading_color": "111827",
        "body_color":    "4B5563",
        "accent_color":  "10B981",
        "slide_bg":      "FFFFFF",
    },
    "product-platform": {
        "heading_font": "Inter",
        "body_font":    "Inter",
        "heading_color": "000000",
        "body_color":    "374151",
        "accent_color":  "2563EB",
        "slide_bg":      "FFFFFF",
    },
    "appendix-heavy": {
        "heading_font": "Helvetica Neue",
        "body_font":    "Helvetica Neue",
        "heading_color": "1F2937",
        "body_color":    "6B7280",
        "accent_color":  "6B7280",
        "slide_bg":      "F9FAFB",
    },
    "template-and-edit": {
        "heading_font": "Arial",
        "body_font":    "Arial",
        "heading_color": "000000",
        "body_color":    "595959",
        "accent_color":  "2563EB",
        "slide_bg":      "FFFFFF",
    },
}

_OVERRIDE_RE = re.compile(r"^([a-z_]+)=(.+)$")


def _load_apply_design_system():
    """Import the sibling script as a module (avoids requiring it on PYTHONPATH)."""
    sibling = Path(__file__).resolve().parent / "apply_design_system.py"
    spec = importlib.util.spec_from_file_location("apply_design_system", sibling)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot locate apply_design_system.py next to {__file__}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_profile(name: str) -> dict[str, Any]:
    if name not in PROFILES:
        raise ValueError(
            f"Unknown profile {name!r}. Available: {sorted(PROFILES)}"
        )
    return dict(PROFILES[name])  # copy so callers can mutate without surprises


def apply_profile(
    pptx: Path,
    profile_name: str,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Apply ``profile_name``'s preset to ``pptx``. Returns the merged spec used."""
    spec = get_profile(profile_name)
    if overrides:
        spec.update(overrides)
    mod = _load_apply_design_system()
    mod.apply_design_system(pptx, spec)
    return spec


def _parse_override(s: str) -> tuple[str, str]:
    m = _OVERRIDE_RE.match(s)
    if not m:
        raise ValueError(f"--override must look like 'key=value', got {s!r}")
    return m.group(1), m.group(2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pptx", nargs="?", type=Path, help="Path to the .pptx (omit for --list / --dump)")
    parser.add_argument("--profile", default=None, help="Profile name (see --list)")
    parser.add_argument("--list", action="store_true", help="List available profiles and exit")
    parser.add_argument("--dump", action="store_true", help="Print the profile's spec JSON and exit")
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        help="key=value, may be repeated. Applied on top of the profile preset.",
    )
    args = parser.parse_args(argv)

    if args.list:
        for name in sorted(PROFILES):
            print(name)
        return 0

    if args.profile is None:
        print("Error: --profile is required (use --list to see options)", file=sys.stderr)
        return 1

    try:
        spec = get_profile(args.profile)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    overrides: dict[str, str] = {}
    for o in args.override:
        try:
            k, v = _parse_override(o)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        overrides[k] = v
    spec.update(overrides)

    if args.dump:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
        return 0

    if args.pptx is None:
        print("Error: pptx path is required when not using --list/--dump", file=sys.stderr)
        return 1
    if not args.pptx.is_file():
        print(f"Error: pptx not found: {args.pptx}", file=sys.stderr)
        return 1

    try:
        applied = apply_profile(args.pptx, args.profile, overrides=overrides)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Applied profile {args.profile!r} to {args.pptx}")
    print(json.dumps(applied, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
