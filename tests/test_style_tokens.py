"""The page's stylesheet keeps to its tokens (docs/DESIGN.md §8.1): every colour, font size, radius
and spacing is a custom property defined in the one token block at the top of style.css, and the
rules below it only use them. No !important anywhere."""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static" / "style.css"
END = "/* end of tokens */"

COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(")
NAMED = re.compile(r"\b(?:white|black|red|green|blue|gr[ae]y|silver|yellow|orange|purple|pink|brown|navy|teal|"
                   r"maroon|olive|lime|aqua|cyan|magenta|fuchsia|gold|beige|ivory|tan|khaki|coral|salmon|crimson|"
                   r"indigo|violet|lavender|plum|orchid|turquoise|wheat|snow|linen|azure|tomato|chocolate)\b")
LENGTH = re.compile(r"(?<![\w-])-?\d*\.?\d+(?:px|r?em|ch|ex|pt|vh|vw|vmin|vmax|dvh)\b")
SPACING = re.compile(r"^(?:margin|padding|gap|row-gap|column-gap|inset|top|right|bottom|left)(?:-.*)?$")
RADIUS = re.compile(r"^border(?:-[a-z]+)*-radius$")


def split() -> tuple[str, str]:
    text = re.sub(r"/\*(?!\s*end of tokens).*?\*/", "", CSS.read_text(), flags=re.S)
    assert END in text, f"style.css has no {END!r} marker after its token block"
    head, rules = text.split(END, 1)
    return head, rules


def declarations(css: str):
    """Each (property, value) in the innermost blocks."""
    for block in re.findall(r"\{([^{}]*)\}", css):
        for decl in block.split(";"):
            if ":" in decl:
                prop, value = decl.split(":", 1)
                yield prop.strip().lower(), value.strip()


def literal_lengths(value: str) -> list[str]:
    return LENGTH.findall(re.sub(r"var\(--[\w-]+\)", "", value))


def test_the_token_block_defines_only_custom_properties_and_the_decided_scales():
    head, _ = split()
    for prop, _value in declarations(head):
        assert prop.startswith("--") or prop == "color-scheme", f"token block: {prop} is not a token"
    names = {p for p, _ in declarations(head) if p.startswith("--")}
    assert sorted(n for n in names if n.startswith("--text-")) == ["--text-lg", "--text-sm", "--text-xl"] and "--text" in names, \
        "four interface type sizes: --text-sm, --text, --text-lg, --text-xl"
    assert sorted(n for n in names if n.startswith("--radius")) == ["--radius", "--radius-menu"], "two radii"


def test_no_literal_colour_size_radius_or_spacing_outside_the_tokens():
    _, rules = split()
    bad = []
    for prop, value in declarations(rules):
        where = f"{prop}: {value}"
        if prop.startswith("--"):
            bad.append(f"a token defined outside the token block: {where}")
        if COLOUR.search(value) or (not prop.startswith("--") and NAMED.search(value) and "var(" not in value):
            bad.append(f"literal colour: {where}")
        if prop in ("font-size", "font") and literal_lengths(value):
            bad.append(f"literal font size: {where}")
        if RADIUS.match(prop) and (literal_lengths(value) or re.search(r"\b\d+%", value) and "50%" not in value):
            bad.append(f"literal radius: {where}")
        if SPACING.match(prop) and literal_lengths(value):
            bad.append(f"literal spacing: {where}")
    assert not bad, "\n".join(bad)


def test_no_important():
    assert "!important" not in CSS.read_text()


def test_the_gate_catches_what_it_should():
    lits = {"color: #fff": True, "padding: 0 var(--sp-2)": False, "margin: -1px": True, "gap: 6px 10px": True,
            "font-size: 12.5px": True, "font-size: var(--text-sm)": False, "top: 50%": False}
    for decl, caught in lits.items():
        prop, value = (x.strip() for x in decl.split(":", 1))
        hit = bool(COLOUR.search(value) or (prop in ("font-size", "font") and literal_lengths(value)) or
                   (SPACING.match(prop) and literal_lengths(value)))
        assert hit == caught, decl
