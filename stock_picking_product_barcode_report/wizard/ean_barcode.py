# Copyright 2026 Nitrokey GmbH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import base64

import barcode  # pylint: disable=missing-manifest-dependency
from barcode.errors import BarcodeError  # pylint: disable=missing-manifest-dependency

from odoo.tools.barcode import get_barcode_check_digit

EAN_L = [
    "0001101",
    "0011001",
    "0010011",
    "0111101",
    "0100011",
    "0110001",
    "0101111",
    "0111011",
    "0110111",
    "0001011",
]
EAN_R = ["".join("1" if b == "0" else "0" for b in code) for code in EAN_L]
EAN_G = [code[::-1] for code in EAN_R]
EAN13_PARITY = [
    "LLLLLL",
    "LLGLGG",
    "LLGGLG",
    "LLGGGL",
    "LGLLGG",
    "LGGLLG",
    "LGGGLL",
    "LGLGLG",
    "LGLGGL",
    "LGGLGL",
]
# Minimum quiet zones (left + right) in modules
EAN_QUIET = {13: 11 + 7, 8: 7 + 7}
CODE128_QUIET = 10 + 10


def ean_modules(code):
    """Return the EAN-8/13 symbol as a string of modules ("1" = bar), or an
    empty string if the code is not a valid EAN-8/13"""
    if (
        len(code) not in EAN_QUIET
        or not code.isdigit()
        or get_barcode_check_digit(code) != int(code[-1])
    ):
        return ""
    if len(code) == 13:
        parity = EAN13_PARITY[int(code[0])]
        left = "".join(
            (EAN_L if p == "L" else EAN_G)[int(d)]
            for p, d in zip(parity, code[1:7], strict=True)
        )
        right = code[7:]
    else:
        left = "".join(EAN_L[int(d)] for d in code[:4])
        right = code[4:]
    return "101" + left + "01010" + "".join(EAN_R[int(d)] for d in right) + "101"


def code128_modules(code):
    """Return the Code 128 symbol as a string of modules ("1" = bar), or an
    empty string if the code can't be encoded"""
    if not code:
        return ""
    try:
        return barcode.get("code128", code).build()[0]
    except BarcodeError:
        return ""


def modules_svg_src(bits):
    """Vector image of the bars, one viewBox unit per module"""
    rects = []
    pos = 0
    while pos < len(bits):
        end = pos
        while end < len(bits) and bits[end] == bits[pos]:
            end += 1
        if bits[pos] == "1":
            rects.append(f'<rect x="{pos}" y="0" width="{end - pos}" height="1"/>')
        pos = end
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{len(bits)}" height="{len(bits) // 4}" '
        f'viewBox="0 0 {len(bits)} 1" preserveAspectRatio="none" '
        f'shape-rendering="crispEdges">{"".join(rects)}</svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
