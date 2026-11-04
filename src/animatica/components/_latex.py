"""LaTeX helpers that never import Manim.

* ``latex_to_markup``: turns simple LaTeX into Pango markup so that, when a real
  LaTeX install is missing or broken, an equation still *looks* like maths
  (F_{n-1} becomes F with a real subscript) instead of raw source code.
* ``explain_latex_failure``: reads the TeX log behind a Manim failure and says
  which package is missing and how to install it.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

# TeX file that could not be found -> CTAN package that provides it.
FILE_TO_PACKAGE = {
    "standalone.cls": "standalone",
    "preview.sty": "preview",
    "amsmath.sty": "amsmath",
    "amssymb.sty": "amsfonts",
    "amsfonts.sty": "amsfonts",
    "babel.sty": "babel",
    "english.ldf": "babel-english",
    "english.sty": "babel-english",
}
# What Manim's default LaTeX template needs, as TinyTeX / TeX Live package names.
REQUIRED_PACKAGES = ("standalone", "preview", "babel-english", "amsmath", "amsfonts", "dvisvgm")

_SYMBOLS = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε", r"\varepsilon": "ε",
    r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ", r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ",
    r"\phi": "φ", r"\varphi": "φ", r"\omega": "ω", r"\Delta": "Δ", r"\Sigma": "Σ", r"\Omega": "Ω", r"\Phi": "Φ",
    r"\cdot": "·", r"\times": "×", r"\div": "÷", r"\pm": "±", r"\mp": "∓", r"\leq": "≤", r"\le": "≤",
    r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠", r"\approx": "≈", r"\equiv": "≡", r"\infty": "∞",
    r"\sum": "∑", r"\prod": "∏", r"\int": "∫", r"\partial": "∂", r"\nabla": "∇", r"\to": "→",
    r"\rightarrow": "→", r"\leftarrow": "←", r"\Rightarrow": "⇒", r"\in": "∈", r"\ldots": "…", r"\dots": "…",
    r"\cdots": "⋯", r"\degree": "°", r"\circ": "°", r"\prime": "′",
}
_STRIP = (r"\left", r"\right", r"\,", r"\;", r"\!", r"\quad", r"\qquad", r"\displaystyle")
_FUNCS = ("sin", "cos", "tan", "log", "ln", "exp", "lim", "max", "min")


def _read_group(s: str, i: int) -> tuple[str, int]:
    """Read one TeX argument starting at s[i]: either {...} or a single token. Returns (text, next_index)."""
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], len(s)
    if s[i] == "\\":
        m = re.match(r"\\[A-Za-z]+", s[i:])
        n = len(m.group(0)) if m else 2
        return s[i:i + n], i + n
    return s[i], i + 1


def _convert(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            m = re.match(r"\\[A-Za-z]+|\\.", s[i:])
            cmd = m.group(0)
            i += len(cmd)
            if cmd == r"\frac" or cmd == r"\dfrac":
                a, i = _read_group(s, i)
                b, i = _read_group(s, i)
                na, nb = _convert(a), _convert(b)
                simple = lambda t: re.fullmatch(r"[\w.]+", re.sub(r"<[^>]+>", "", t)) is not None  # noqa: E731
                out.append((na if simple(na) else f"({na})") + "/" + (nb if simple(nb) else f"({nb})"))
            elif cmd == r"\sqrt":
                a, i = _read_group(s, i)
                out.append("√(" + _convert(a) + ")")
            elif cmd in (r"\text", r"\mathrm", r"\mathbf", r"\operatorname", r"\mathit"):
                a, i = _read_group(s, i)
                out.append(escape(a))
            elif cmd in _STRIP:
                continue
            elif cmd in _SYMBOLS:
                out.append(_SYMBOLS[cmd])
            elif cmd[1:] in _FUNCS:
                out.append(cmd[1:])
            elif cmd in (r"\{", r"\}", r"\%", r"\&", r"\_", r"\#"):
                out.append(escape(cmd[1]))
            else:
                out.append(escape(cmd[1:]))  # unknown command: show its name rather than a backslash
        elif ch in "_^":
            tag = "sub" if ch == "_" else "sup"
            a, i = _read_group(s, i + 1)
            out.append(f"<{tag}>{_convert(a)}</{tag}>")
        elif ch in "{}":
            i += 1
        elif ch == "~":
            out.append(" ")
            i += 1
        else:
            out.append(escape(ch, quote=False))
            i += 1
    return "".join(out)


def latex_to_markup(latex: str) -> str:
    """Best-effort LaTeX -> Pango markup (<sub>/<sup>, Greek, operators). Never raises."""
    try:
        return _convert(latex.strip())
    except Exception:  # pragma: no cover - defensive: fall back to escaped source
        return escape(latex)


def latex_to_plain(latex: str) -> str:
    """Readable plain text for captions/logs: F_{n-1} -> F_(n-1), a^2 -> a^2."""
    marked = latex_to_markup(latex)
    marked = re.sub(r"<sub>(.*?)</sub>", lambda m: "_" + (m.group(1) if len(m.group(1)) == 1 else f"({m.group(1)})"), marked)
    marked = re.sub(r"<sup>(.*?)</sup>", lambda m: "^" + (m.group(1) if len(m.group(1)) == 1 else f"({m.group(1)})"), marked)
    marked = re.sub(r"<[^>]+>", "", marked)
    from html import unescape
    return unescape(marked)


_LOG_HINT = re.compile(r"log file:\s*(\S.*?\.log)\s*$", re.M)


def _tail_reason(log_text: str) -> tuple[str, list[str]]:
    """Return (one-line reason, list of CTAN packages that look missing) from a TeX log."""
    packages: list[str] = []
    reason = ""
    for m in re.finditer(r"File [`'](.+?)' not found", log_text):
        fname = m.group(1)
        pkg = FILE_TO_PACKAGE.get(fname) or FILE_TO_PACKAGE.get(Path(fname).name)
        if pkg and pkg not in packages:
            packages.append(pkg)
        reason = reason or f"TeX file {fname} not found"
    if re.search(r"Unknown option [`']?english|babel.*english", log_text, re.S) and "babel-english" not in packages:
        packages.append("babel-english")
        reason = reason or "babel language 'english' not installed"
    if not reason:
        bang = re.search(r"^! (.+)$", log_text, re.M)
        reason = bang.group(1).strip() if bang else "LaTeX could not compile"
    return reason, packages


def install_hint(packages: list[str]) -> str:
    pk = " ".join(dict.fromkeys(list(packages) + list(REQUIRED_PACKAGES)))
    return f"tlmgr install {pk}"


def explain_latex_failure(exc: BaseException) -> str:
    """Turn a Manim LaTeX exception into a short, actionable sentence."""
    msg = str(exc)
    m = _LOG_HINT.search(msg)
    reason, packages = "", []
    if m:
        try:
            reason, packages = _tail_reason(Path(m.group(1)).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    if not reason:
        if "latex" in msg.lower() or "dvisvgm" in msg.lower():
            reason = msg.splitlines()[0][:160] if msg else type(exc).__name__
        else:
            reason = f"{type(exc).__name__}: {msg[:160]}" if msg else type(exc).__name__
    if packages:
        return f"{reason}. Fix: run `{install_hint(packages)}` then `animatica doctor`"
    return f"{reason}. Run `animatica doctor` to check your LaTeX install"

