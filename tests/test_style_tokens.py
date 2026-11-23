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


def test_a_loop_row_made_a_button_keeps_the_rows_look():
    """The side panel's loop rows are buttons (for the keyboard): the stylesheet takes off the button's own border,
    fill and centring, so a row still reads as a row of the list."""
    _, rules = split()
    found = [dict(declarations("{" + body + "}")) for body in re.findall(r"button\.looprow\s*\{([^{}]*)\}", rules)]
    assert found, "style.css has no button.looprow rule"
    rule = found[0]
    assert rule.get("border") == "0" and rule.get("background") == "none" and rule.get("text-align") == "left", rule


def test_the_gate_catches_what_it_should():
    lits = {"color: #fff": True, "padding: 0 var(--sp-2)": False, "margin: -1px": True, "gap: 6px 10px": True,
            "font-size: 12.5px": True, "font-size: var(--text-sm)": False, "top: 50%": False}
    for decl, caught in lits.items():
        prop, value = (x.strip() for x in decl.split(":", 1))
        hit = bool(COLOUR.search(value) or (prop in ("font-size", "font") and literal_lengths(value)) or
                   (SPACING.match(prop) and literal_lengths(value)))
        assert hit == caught, decl


def test_below_760_px_the_tabs_wrap_and_never_scroll_sideways():
    """The narrow-width half of tests/test_items_page.py's phone/200% check, readable without a browser: below 760 px
    the nav wraps onto its own rows, nothing in the sheet makes it scroll sideways, and the current page keeps its
    underline."""
    text = re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.S)
    narrow = re.search(r"@media \(max-width: 759px\) \{(.*?)\n\}", text, flags=re.S)
    assert narrow, "no @media (max-width: 759px) block"
    nav = dict(declarations(re.search(r"\.bar nav \{[^{}]*\}", narrow.group(1)).group(0)))
    assert nav.get("flex-wrap") == "wrap" and nav.get("overflow-x") == "visible", nav
    for block in re.findall(r"@media \(max-width: (\d+)px\) \{(.*?)\n\}", text, flags=re.S):
        if int(block[0]) < 760:
            for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block[1]):
                if sel.strip().startswith(".bar nav") and "a" not in sel.split():
                    assert dict(declarations("{" + body + "}")).get("overflow-x", "visible") == "visible", sel
    assert "border-bottom-color: var(--ink)" in re.search(r"\.bar nav a\.on \{[^{}]*\}", text).group(0)


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


def test_the_arrows_and_guide_dot_borders_stand_3_to_1_on_the_paper_in_both_themes():
    """The /item lifecycle and /items state arrows (.arrow) and the Guide's dot borders (.g-dot::before, the dot drawn
    inside its 24px target) are graphics: WCAG's 3:1 against the page in the light and the dark theme, read from the
    tokens they use."""
    head, rules = split()
    light_head, dark_head = head.split("prefers-color-scheme: dark", 1)
    themes = {"light": dict(re.findall(r"(--[\w-]+):\s*([^;]+);", light_head))}
    themes["dark"] = {**themes["light"], **dict(re.findall(r"(--[\w-]+):\s*([^;]+);", dark_head))}
    arrow = re.search(r"(?m)^\.arrow\s*\{[^}]*\bcolor:\s*var\((--[\w-]+)\)", rules)
    dot = re.search(r"(?m)^\.g-dot::before\s*\{[^}]*\bborder:[^;]*var\((--[\w-]+)\)\s*;", rules)
    assert arrow and dot, "the .arrow colour and the .g-dot::before border are each one token"
    low = []
    for theme, tokens in themes.items():
        bg = _luminance(_oklab(tokens["--bg"].strip()))
        for what, token in (("arrow", arrow[1]), ("guide dot border", dot[1])):
            y = _luminance(_oklab(tokens[token].strip()))
            ratio = (max(y, bg) + 0.05) / (min(y, bg) + 0.05)
            if ratio < 3:
                low.append(f"{theme} {what} ({token}): {ratio:.2f}")
    assert not low, low


def test_the_diagrams_keyboard_focus_ring_is_the_accent_and_stands_3_to_1_in_both_themes():
    """Done item 5 of diagram-roving-focus-and-arrow-keys, readable without a browser: the ring keys.js's roving focus
    shows on a diagram part (its outline, and the part's own outline stroke) is the accent token, and the accent
    stands 3:1 against the page in the light and the dark theme. tests/test_diagram_rendering.py checks it is drawn."""
    head, rules = split()
    light_head, dark_head = head.split("prefers-color-scheme: dark", 1)
    themes = {"light": dict(re.findall(r"(--[\w-]+):\s*([^;]+);", light_head))}
    themes["dark"] = {**themes["light"], **dict(re.findall(r"(--[\w-]+):\s*([^;]+);", dark_head))}
    ring = re.search(r"svg\.canvas \[data-key\]:focus-visible\s*\{([^{}]*)\}", rules)
    stroke = re.search(r"svg\.canvas \.node:focus-visible \.hit[^{]*\{([^{}]*)\}", rules)
    assert ring and stroke, "style.css has no focus ring for a diagram part"
    assert re.search(r"outline:\s*\d+px solid var\(--accent\)", ring[1]), ring[1]
    assert "stroke: var(--accent)" in stroke[1], stroke[1]
    low = []
    for theme, tokens in themes.items():
        y, bg = _luminance(_oklab(tokens["--accent"].strip())), _luminance(_oklab(tokens["--bg"].strip()))
        ratio = (max(y, bg) + 0.05) / (min(y, bg) + 0.05)
        if ratio < 3:
            low.append(f"{theme}: {ratio:.2f}")
    assert not low, low


def test_the_first_level_note_sits_on_the_canvas_and_stacks_with_the_toolbar_on_a_narrow_screen():
    """'Open all' on a model too big to read opens the first level and says so in a note diagram.js draws as
    .open-level: it has its rule, sits over the canvas in small text, and goes static with .toolbar and .zoom."""
    js = (CSS.parent / "diagram.js").read_text()
    assert 'class: "open-level"' in js, "diagram.js no longer draws the first-level note as .open-level"
    _, rules = split()
    own = re.search(r"(?:^|\})\s*\.open-level\s*\{([^{}]*)\}", rules)
    assert own, "style.css has no rule of its own for .open-level"
    decls = dict(declarations("{" + own.group(1) + "}"))
    assert decls.get("position") == "absolute" and decls.get("font-size") == "var(--text-sm)", decls
    narrow = [sel for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", rules)
              if "position: static" in body and ".toolbar" in sel]
    assert any(".open-level" in sel for sel in narrow), "on a narrow screen the note stays absolute over the toolbar"


def test_the_diagram_left_while_another_opens_is_dimmed_and_cannot_be_clicked():
    """Into, Open (ui-open-into-and-every-panel-link-show-that-somethi): the diagram left stays on the screen, dimmed,
    under 'Opening …', with its side list; neither may take a click meant for the diagram being opened."""
    _, rules = split()
    for sel in ("svg.canvas g.was", ".diagram.opening > .side"):
        block = next((b for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", rules)
                      if sel in [x.strip() for x in s.split(",")]), None)
        assert block is not None, f"no rule for {sel}"
        decl = dict(declarations("{" + block + "}"))
        assert float(decl.get("opacity", "1")) < 1, f"{sel} is not dimmed"
        assert decl.get("pointer-events") == "none", f"{sel} still takes clicks"


def test_a_blocks_loop_state_is_bold_when_off_and_never_a_colour():
    """Blocks has no status colour (docs/DESIGN.md's colour rules): the state blocks.js prints on a loop's error label
    (.bd-state, .bd-off when the server's word is off) is set in ink, the off one only bolder, and no rule naming
    either class gives it a colour, a fill or a stroke. The browser half is in tests/test_diagram_rendering.py."""
    js = (CSS.parent / "blocks.js").read_text()
    assert 'st.word === "off" ? " bd-off"' in js, "blocks.js no longer marks the off word with .bd-off"
    _, rules = split()
    found = [(sel.strip(), dict(declarations("{" + body + "}")))
             for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", rules) if "bd-state" in sel or "bd-off" in sel]
    assert any("bd-off" in s and d.get("font-weight") == "600" for s, d in found), found
    painted = [(s, p) for s, d in found for p in d if p in ("color", "fill", "stroke", "background", "opacity")]
    assert not painted, painted


def test_the_dark_tokens_stand_aside_while_a_picture_is_exported():
    """A saved picture is drawn light whatever the theme: each dark-theme rule excludes the class export.js sets on
    <html> while it reads the drawing's styles, and export.js sets and then clears that very class."""
    head, _ = split()
    selectors = [s.strip() for s in re.findall(r"([^{}]+)\{[^{}]*\}", head.split("prefers-color-scheme: dark", 1)[1])]
    assert selectors and all(s.endswith(":not(.export-light)") for s in selectors), selectors
    js = (CSS.parent / "export.js").read_text()
    assert 'classList.add("export-light")' in js and 'classList.remove("export-light")' in js
