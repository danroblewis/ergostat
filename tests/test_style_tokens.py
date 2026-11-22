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


def _oklab(hexc: str) -> list[float]:
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(hexc[i:i + 2], 16) / 255) for i in (1, 3, 5))
    lms = [(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3),
           (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3),
           (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)]
    m = ((0.2104542553, 0.7936177850, -0.0040720468), (1.9779984951, -2.4285922050, 0.4505937099),
         (0.0259040371, 0.7827717662, -0.8086757660))
    return [sum(a * x for a, x in zip(row, lms, strict=True)) for row in m]


def _luminance(lab: list[float]) -> float:
    L, a, b = lab
    l_, m_, s_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, \
        (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = [4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_, -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_]
    r, g, b = (min(max(c, 0.0), 1.0) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_dark_theme_correspondence_colours_stand_3_to_1_on_the_paper():
    """WCAG's 3:1 for graphics: every correspondence colour in the dark theme, the hue and its repeats toward the ink
    and toward the paper (colours.js's color-mix in oklab), against the dark paper."""
    head, _ = split()
    dark = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", head.split("prefers-color-scheme: dark", 1)[1]))
    js = (CSS.parent / "colours.js").read_text()
    assert "${hue} var(--g-fade), var(--bg)" in js and "${hue} 62%, var(--ink)" in js
    bg, ink, fade = _oklab(dark["--bg"].strip()), _oklab(dark["--ink"].strip()), float(dark["--g-fade"].strip(" %")) / 100
    low = []
    for i in range(10):
        hue = _oklab(dark[f"--g{i}"].strip())
        for step, lab in (("hue", hue), ("toward the ink", [0.62 * h + 0.38 * k for h, k in zip(hue, ink, strict=True)]),
                          ("toward the paper", [fade * h + (1 - fade) * p for h, p in zip(hue, bg, strict=True)])):
            ya, yb = _luminance(lab), _luminance(bg)
            ratio = (max(ya, yb) + 0.05) / (min(ya, yb) + 0.05)
            if ratio < 3:
                low.append(f"--g{i} {step}: {ratio:.2f}")
    assert not low, low


def test_on_a_phone_the_direction_hint_is_not_hidden():
    """The narrow layout shows the "More beyond the edge" hint (a phone's first view may be centred on one part): no
    rule inside a max-width media block hides .panhint. The browser test pins what the hint says."""
    text = re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.S)
    blocks = re.findall(r"@media[^{]*max-width[^{]*\{((?:[^{}]*\{[^{}]*\})*[^{}]*)\}", text)
    assert blocks, "style.css has no narrow (max-width) layout"
    for block in blocks:
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block):
            if ".panhint" in sel:
                assert not re.search(r"display\s*:\s*none", body), f"the phone layout hides the hint: {sel.strip()}"
