"""Lecture des relevés CSV bancaires : détection du format, des colonnes, parsing."""
import csv
import hashlib
import io
import re
import unicodedata
from collections import Counter
from datetime import datetime

DATE_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"]


def decode(raw: bytes) -> str:
    """Les banques françaises exportent souvent en cp1252 plutôt qu'en UTF-8."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def parse_amount(value: str) -> float | None:
    s = (value or "").strip().replace(" ", "").replace(" ", "").replace(" ", "")
    s = s.replace("€", "").replace("EUR", "").replace("+", "")
    if not s:
        return None
    negative = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()")
    if "," in s and "." in s:
        # Le dernier séparateur est le séparateur décimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if negative else n


def parse_date(value: str) -> str | None:
    s = (value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def detect_delimiter(text: str) -> str:
    """Choisit le séparateur qui donne le plus de lignes ayant le même nombre (≥ 2) de colonnes.
    (csv.Sniffer se trompe souvent à cause des montants à virgule décimale.)"""
    lines = [l for l in text.splitlines()[:200] if l.strip()]
    best, best_score = ";", -1
    for d in (";", "\t", ",", "|"):
        counts = Counter(len(r) for r in csv.reader(lines, delimiter=d))
        width, freq = counts.most_common(1)[0] if counts else (0, 0)
        score = freq if width >= 2 else 0
        if score > best_score:
            best, best_score = d, score
    return best


def read_rows(text: str) -> tuple[list[str], list[list[str]], str]:
    """Retourne (en-têtes, lignes, délimiteur) en sautant le préambule éventuel."""
    delimiter = detect_delimiter(text)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    if not rows:
        return [], [], delimiter
    # Beaucoup de banques mettent des lignes d'info (n° de compte, solde…) avant le tableau :
    # l'en-tête est la première ligne ayant le nombre de colonnes le plus fréquent.
    width = Counter(len(r) for r in rows).most_common(1)[0][0]
    start = next(i for i, r in enumerate(rows) if len(r) == width)
    header = [h.strip() for h in rows[start]]
    body = [r + [""] * (width - len(r)) for r in rows[start + 1:] if len(r) >= width - 1]
    return header, body, delimiter


def guess_mapping(header: list[str], body: list[list[str]]) -> dict:
    """Devine les colonnes date / libellé / montant (ou débit + crédit)."""
    norm = [_strip_accents(h).lower() for h in header]

    def find(*keywords, exclude=()):
        for i, h in enumerate(norm):
            if any(k in h for k in keywords) and not any(e in h for e in exclude):
                return i
        return None

    mapping = {
        "date": find("date op", "date"),
        "label": find("libelle", "label", "description", "intitule", "detail", "operation", "nature", exclude=("date",)),
        "label2": None,
        "amount": find("montant", "amount", "somme", "valeur", exclude=("date",)),
        "debit": find("debit"),
        "credit": find("credit"),
    }
    if mapping["date"] is None and body:
        mapping["date"] = next((i for i, v in enumerate(body[0]) if parse_date(v)), None)
    if mapping["debit"] is not None and mapping["credit"] is not None:
        mapping["amount"] = None
    if mapping["label"] == mapping["date"]:
        mapping["label"] = None
    return mapping


def normalize_label(label: str) -> str:
    """Libellé simplifié pour repérer les opérations similaires (sans dates, n°, etc.)."""
    s = _strip_accents(label).upper()
    s = re.sub(r"\d+", " ", s)
    s = re.sub(r"\b(CB|PRLV|SEPA|VIR|CARTE|FACTURE|X+)\b", " ", s)
    s = re.sub(r"[^A-Z ]", " ", s)
    return " ".join(s.split())[:40]


def parse_transactions(header, body, mapping) -> tuple[list[dict], list[str]]:
    def col(row, key):
        idx = mapping.get(key)
        return row[idx].strip() if idx is not None and idx != "" and int(idx) < len(row) else ""

    mapping = {k: (int(v) if v not in (None, "") else None) for k, v in mapping.items()}
    out, errors = [], []
    for n, row in enumerate(body, start=1):
        date = parse_date(col(row, "date"))
        label = " ".join(x for x in (col(row, "label"), col(row, "label2")) if x)
        if mapping.get("amount") is not None:
            amount = parse_amount(col(row, "amount"))
        else:
            debit, credit = parse_amount(col(row, "debit")), parse_amount(col(row, "credit"))
            if debit is None and credit is None:
                amount = None
            else:
                amount = (abs(credit) if credit else 0.0) - (abs(debit) if debit else 0.0)
        if date is None or amount is None:
            errors.append(f"Ligne {n} ignorée : {';'.join(row)[:80]}")
            continue
        out.append({"date": date, "label": label or "(sans libellé)", "amount": round(amount, 2)})
    return out, errors


def tx_hash(account_id: int, tx: dict, occurrence: int) -> str:
    """Empreinte pour éviter les doublons lors de ré-imports d'un même relevé.
    `occurrence` distingue deux opérations strictement identiques le même jour."""
    key = f"{account_id}|{tx['date']}|{tx['label']}|{tx['amount']:.2f}|{occurrence}"
    return hashlib.sha1(key.encode()).hexdigest()
