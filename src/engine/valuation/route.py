"""Headline routing (D-M08-1, rule 3): which standard row becomes `valuation_multiple`.

Routing never hides a row (D10, D32): it chooses only the headline and its weight.

Order (first that applies):
1. Owner override `headline` in `config/valuation.toml`.
2. Model tag (D-M04-8): `asset_treasury` → mNAV (D-M08-7); `fund` → `not_applicable`;
   `financial` / `reit` (and untagged FF12 group 11) → `not_applicable` (banks: P/B, REITs:
   FFO are open for the owner; the standard rows, P/B included, are shown).
3. Cyclical flag (computed or owner) → EV ÷ normalized EBIT (P ÷ normalized EPS beside);
   it overrides the stage, an unconfirmed one included (MU).
4. M04's confirmed stage: introduction / growth → EV/Sales (EV/GP beside); mature → P/E TTM
   (EV/EBIT beside); shake-out → EV ÷ normalized EBIT; decline → EV/EBIT (P/B beside).
5. Otherwise `stage_unconfirmed`: value NULL, every timeframe info.

A headline that is `not_meaningful` reads `not_meaningful` (the other rows still show the
alternatives); an EV headline with EV incomplete takes P/S as the value, "EV incomplete" in
`method` (rule 3, case 4).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.valuation.measures import EV_ROWS, LABELS, NM, Snapshot

BY_STAGE = {
    "introduction": ("val_ev_sales", "val_ev_gp"),
    "growth": ("val_ev_sales", "val_ev_gp"),
    "mature": ("val_pe_ttm", "val_ev_ebit"),
    "shake_out": ("val_ev_nebit", "val_p_neps"),
    "decline": ("val_ev_ebit", "val_pb"),
}
CYCLICAL = ("val_ev_nebit", "val_p_neps")
BESIDE = {a: b for a, b in BY_STAGE.values()} | {"mnav": "val_pb"}


@dataclass
class Route:
    measure: str | None  # a val_* row or mnav; None → `code`
    code: str | None  # stage_unconfirmed | not_applicable
    why: str
    beside: str | None = None
    basis: str = ""  # short: owner override, model tag, cyclical, stage <x>, stage unconfirmed

    @property
    def scored(self) -> bool:
        return self.measure is not None


def choose(
    *,
    stage: str | None,
    stage_text: str,
    cyclical: bool | None,
    tag: str | None,
    tag_text: str = "",
    override_headline: str | None = None,
    override_reason: str = "",
) -> Route:
    if override_headline:
        return Route(
            override_headline,
            None,
            f"owner override: {override_reason}",
            BESIDE.get(override_headline),
            "owner override",
        )
    if tag == "asset_treasury":
        return Route(
            "mnav",
            None,
            f"{tag_text}: mNAV, crypto exposure (scope S1; D-M08-7)",
            "val_pb",
            "model tag asset_treasury",
        )
    if tag == "fund":
        return Route(
            None,
            "not_applicable",
            f"{tag_text}: not applicable (fund, D-M04-8)",
            basis="model tag fund",
        )
    if tag in ("financial", "reit"):
        return Route(
            None,
            "not_applicable",
            f"{tag_text}: no headline routed (banks P/B, REITs "
            "FFO: open for the owner); standard rows shown (D32)",
            basis=f"model {tag}",
        )
    if cyclical:
        return Route(
            CYCLICAL[0],
            None,
            f"cyclical flag overrides the stage ({stage_text})",
            CYCLICAL[1],
            "cyclical",
        )
    if stage in BY_STAGE:
        a, b = BY_STAGE[stage]
        return Route(a, None, f"stage {stage} (confirmed)", b, f"stage {stage}")
    return Route(
        None,
        "stage_unconfirmed",
        f"{stage_text}: no headline until the owner confirms "
        "the stage (D-M04-7); every measure shown",
        basis="stage unconfirmed",
    )


@dataclass
class Headline:
    value: float | None
    text: str | None  # value_text
    measure: str | None  # what the value is (P/S when EV incomplete)
    method: str
    missing: str | None = None


def headline(r: Route, s: Snapshot) -> Headline:
    if r.measure is None:
        return Headline(None, r.code, None, r.why)
    m = s.m(r.measure)
    label = LABELS[r.measure]
    if m.missing and r.measure in EV_ROWS and m.missing.startswith("EV incomplete"):
        ps = s.m("val_ps")
        if ps.value is not None:
            return Headline(
                ps.value,
                None,
                "val_ps",
                f"{label} → P/S {ps.value:.1f}× (EV incomplete: {s.ev_missing}; rule 3); {r.why}",
            )
        return Headline(
            None, None, None, f"{label}; {r.why}", f"{m.missing}; P/S {ps.missing or ps.text}"
        )
    if m.missing:
        return Headline(None, None, None, f"{label}; {r.why}", m.missing)
    if m.value is None:
        return Headline(None, m.text or NM, r.measure, f"{label} {m.text or NM}; {r.why}")
    return Headline(
        m.value,
        m.text if m.text and m.text != NM else None,
        r.measure,
        f"{label} {m.shown}; {r.why}",
    )
