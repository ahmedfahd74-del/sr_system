#!/usr/bin/env python3
"""Static regression audit for the post-D20 SwingTech hardening invariants."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PINE = ROOT / "pinescripts" / "swingtech_rebuild.pine"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    source = PINE.read_text(encoding="utf-8")

    # One numeric score implementation, consumed by decision, display and focus.
    require(source.count("f_levelScore(") == 5, "expected one score definition and four consumers")
    require("f_locScore" not in source, "legacy decision-only score remains")
    score_body = source.split("f_levelScore(int _i) =>", 1)[1].split("// The published selection", 1)[0]
    require("conflCrossType" in score_body, "canonical score ignores cross-type setting")
    require("if scFold" in score_body and "f_provenMult" in score_body, "canonical score ignores record fold")

    # LOC latches may only advance on a confirmed chart bar.
    loc_block = source.split("[_lbM, _lbT, _lbB, _lsM2, _lsT2, _lsB2]", 1)[1].split("// only draw", 1)[0]
    require("if barstate.isconfirmed" in loc_block, "LOC FVG latch is not confirmation-gated")

    # Every registry-handle setter outside f_lvlDraw has a local handle guard.
    guarded = (
        "if not na(_hs.ln)\n                line.set_color(_hs.ln",
        "if not na(_a.ln)\n                line.set_width(_a.ln",
        "if not na(_a.ln)\n                line.set_color(_a.ln, color.new",
        "if not na(_s2.ln)\n                line.set_color(_s2.ln",
    )
    for snippet in guarded:
        require(snippet in source, f"missing handle guard: {snippet.splitlines()[-1].strip()}")

    # ARMED persists, while GO is consumed once per armed setup.
    require("var bool goConsumed = false" in source, "one-shot GO latch missing")
    require("bool goFire = barstate.isconfirmed and goArmed and not goConsumed" in source, "GO is not a confirmed one-shot")
    require("bool _trFire = exLong or exShort" in source, "tracker still reconstructs an edge from persistent GO")

    # Parity compares a common event, not chart-history-dependent totals.
    require("f_regCount" not in source and "f_regLive" not in source, "raw count parity remains")
    require("f_regNewestState" in source, "event identity/state parity diagnostic missing")
    require(source.count("BOS source time\"") == 3, "W/D/4H source-time parity plots missing")
    require(source.count("BOS state\"") == 3, "W/D/4H lifecycle parity plots missing")

    # One FVG rule and no remaining inline leg-copy inequalities.
    code = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
    require(code.count("f_fvgRaw(") == 4, "expected one FVG definition and three consumers")
    require(not re.search(r"low\[i\]\s*>\s*high\[i\s*\+\s*2\]", source), "inline bullish leg FVG remains")
    require(not re.search(r"high\[i\]\s*<\s*low\[i\s*\+\s*2\]", source), "inline bearish leg FVG remains")

    # Dead intermediary and case-only input identifiers are gone from code.
    require(not re.search(r"\bhasLeg\b", code), "dead hasLeg variable remains")
    require(not re.search(r"\bshowLS\b|\bshowLs\b", code), "case-only sweep identifiers remain")
    require("showLegSweep" in code and "showPoolSweep" in code, "explicit sweep identifiers missing")

    # Basic file-integrity checks independent of the repository linter.
    require("\t" not in source, "tab character found")
    require(source.count("(") == source.count(")"), "parenthesis count mismatch")
    require(source.count("[") == source.count("]"), "bracket count mismatch")

    print("SwingTech hardening static audit: PASS")


if __name__ == "__main__":
    main()
