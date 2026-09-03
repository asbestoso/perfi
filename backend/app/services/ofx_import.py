"""Minimal OFX parser: STMTTRN blocks become staging rows.

Handles the common bank-export shape (<STMTTRN> with DTPOSTED/TRNAMT/NAME/
MEMO/FITID). Not a full OFX implementation: headers are skipped, unclosed
tags are tolerated by regex, investment (BUYMF etc.) blocks are ignored.
"""
import datetime as dt
import re

from .csv_import import stage_rows


def _tag(block, name):
    m = re.search(r"<%s>([^\r\n<]*)" % name, block)
    return m.group(1).strip() if m else ""


def parse_ofx(raw):
    text = raw.decode("utf-8", errors="replace")
    start = text.find("<OFX>")
    if start != -1:
        text = text[start:]
    out = []
    for block in re.split(r"<STMTTRN>", text)[1:]:
        end = block.find("</STMTTRN>")
        if end != -1:
            block = block[:end]
        stamp = _tag(block, "DTPOSTED")[:8]
        try:
            date = dt.datetime.strptime(stamp, "%Y%m%d").date()
        except ValueError:
            continue
        try:
            cents = round(float(_tag(block, "TRNAMT")) * 100)
        except ValueError:
            continue
        merchant = _tag(block, "NAME") or _tag(block, "MEMO")
        memo = _tag(block, "MEMO")
        if memo and memo != merchant:
            merchant = f"{merchant} {memo}".strip()
        out.append(({"date": date, "merchant": merchant, "amount_cents": cents,
                     "category": "", "note": memo},
                    {"fitid": _tag(block, "FITID"), "memo": memo}))
    return out


def import_ofx(db, account_id, raw, filename=""):
    return stage_rows(db, account_id, "ofx", filename, parse_ofx(raw))
