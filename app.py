"""Application locale de suivi des dépenses — lancer avec : python app.py"""
import json
import sys
import uuid
import webbrowser
from collections import defaultdict
from datetime import date
from pathlib import Path
from threading import Timer

from flask import Flask, jsonify, request, send_from_directory

import importer
from db import connect, init_db

# Dans l'exécutable PyInstaller, les fichiers embarqués sont décompressés dans sys._MEIPASS
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
app = Flask(__name__, static_folder=str(BASE_DIR / "static"))

# Type effectif d'une opération : celui de sa catégorie, sinon déduit du signe du montant
KIND_SQL = "COALESCE(c.kind, CASE WHEN t.amount < 0 THEN 'expense' ELSE 'income' END)"


def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def error(msg, code=400):
    return jsonify({"error": msg}), code


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------- Comptes / catégories
CRUD_TABLES = {
    "accounts": ("name", "color"),
    "categories": ("name", "color", "kind"),
}


@app.get("/api/<table>")
def list_items(table):
    if table not in CRUD_TABLES:
        return error("Inconnu", 404)
    fk = "account_id" if table == "accounts" else "category_id"
    with connect() as conn:
        return jsonify(rows(conn.execute(f"""
            SELECT x.*, (SELECT COUNT(*) FROM transactions t WHERE t.{fk} = x.id) AS tx_count
            FROM {table} x ORDER BY x.name COLLATE NOCASE""")))


@app.post("/api/<table>")
def create_item(table):
    if table not in CRUD_TABLES:
        return error("Inconnu", 404)
    data = request.json or {}
    fields = [f for f in CRUD_TABLES[table] if f in data]
    if not data.get("name", "").strip():
        return error("Le nom est obligatoire")
    try:
        with connect() as conn:
            cur = conn.execute(
                f"INSERT INTO {table}({','.join(fields)}) VALUES ({','.join('?' * len(fields))})",
                [data[f].strip() if f == "name" else data[f] for f in fields],
            )
            return jsonify({"id": cur.lastrowid})
    except Exception as e:  # nom déjà utilisé
        return error(str(e))


@app.put("/api/<table>/<int:item_id>")
def update_item(table, item_id):
    if table not in CRUD_TABLES:
        return error("Inconnu", 404)
    data = request.json or {}
    fields = [f for f in CRUD_TABLES[table] if f in data]
    if not fields:
        return jsonify({"ok": True})
    try:
        with connect() as conn:
            conn.execute(
                f"UPDATE {table} SET {', '.join(f + '=?' for f in fields)} WHERE id=?",
                [data[f] for f in fields] + [item_id],
            )
    except Exception as e:
        return error(str(e))
    return jsonify({"ok": True})


@app.delete("/api/<table>/<int:item_id>")
def delete_item(table, item_id):
    if table not in CRUD_TABLES:
        return error("Inconnu", 404)
    with connect() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Règles
@app.get("/api/rules")
def list_rules():
    with connect() as conn:
        return jsonify(rows(conn.execute("""
            SELECT r.*, c.name AS category_name, c.color AS category_color
            FROM rules r LEFT JOIN categories c ON c.id = r.category_id
            ORDER BY r.pattern COLLATE NOCASE""")))


@app.post("/api/rules")
def create_rule():
    data = request.json or {}
    pattern = data.get("pattern", "").strip()
    if not pattern:
        return error("Le motif est obligatoire")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO rules(pattern, category_id, recurring) VALUES (?, ?, ?)",
            (pattern, data.get("category_id") or None, data.get("recurring")),
        )
        rule_id = cur.lastrowid
        applied = apply_rules(conn, only_uncategorized=True)
    return jsonify({"id": rule_id, "applied": applied})


@app.put("/api/rules/<int:rule_id>")
def update_rule(rule_id):
    data = request.json or {}
    with connect() as conn:
        conn.execute(
            "UPDATE rules SET pattern=?, category_id=?, recurring=? WHERE id=?",
            (data["pattern"].strip(), data.get("category_id") or None, data.get("recurring"), rule_id),
        )
    return jsonify({"ok": True})


@app.delete("/api/rules/<int:rule_id>")
def delete_rule(rule_id):
    with connect() as conn:
        conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    return jsonify({"ok": True})


def apply_rules(conn, only_uncategorized=True, tx_ids=None) -> int:
    """Applique les règles (la plus longue / spécifique gagne). Retourne le nb d'opérations modifiées."""
    rules = conn.execute("SELECT * FROM rules ORDER BY LENGTH(pattern) DESC").fetchall()
    if not rules:
        return 0
    sql = "SELECT id, label, category_id, recurring FROM transactions"
    cond, params = [], []
    if only_uncategorized:
        cond.append("category_id IS NULL")
    if tx_ids is not None:
        if not tx_ids:
            return 0
        cond.append(f"id IN ({','.join('?' * len(tx_ids))})")
        params += tx_ids
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    changed = 0
    for tx in conn.execute(sql, params).fetchall():
        label = tx["label"].lower()
        rule = next((r for r in rules if r["pattern"].lower() in label), None)
        if not rule:
            continue
        cat = rule["category_id"] if rule["category_id"] is not None else tx["category_id"]
        rec = rule["recurring"] if rule["recurring"] is not None else tx["recurring"]
        if (cat, rec) != (tx["category_id"], tx["recurring"]):
            conn.execute("UPDATE transactions SET category_id=?, recurring=? WHERE id=?", (cat, rec, tx["id"]))
            changed += 1
    return changed


@app.post("/api/rules/apply")
def apply_rules_route():
    data = request.json or {}
    with connect() as conn:
        n = apply_rules(conn, only_uncategorized=data.get("only_uncategorized", True))
    return jsonify({"applied": n})


# ---------------------------------------------------------------- Opérations
@app.get("/api/transactions")
def list_transactions():
    a = request.args
    cond, params = [], []
    if a.get("month"):
        cond.append("substr(t.date, 1, 7) = ?")
        params.append(a["month"])
    if a.get("account"):
        cond.append("t.account_id = ?")
        params.append(a["account"])
    if a.get("category") == "none":
        cond.append("t.category_id IS NULL")
    elif a.get("category"):
        cond.append("t.category_id = ?")
        params.append(a["category"])
    if a.get("recurring") in ("0", "1"):
        cond.append("t.recurring = ?")
        params.append(int(a["recurring"]))
    if a.get("q"):
        cond.append("(t.label LIKE ? OR t.note LIKE ?)")
        params += [f"%{a['q']}%"] * 2
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    with connect() as conn:
        return jsonify(rows(conn.execute(f"""
            SELECT t.*, a.name AS account_name, a.color AS account_color
            FROM transactions t JOIN accounts a ON a.id = t.account_id
            LEFT JOIN categories c ON c.id = t.category_id
            {where} ORDER BY t.date DESC, t.id DESC LIMIT 5000""", params)))


@app.patch("/api/transactions")
def update_transactions():
    """Modification d'une ou plusieurs opérations : {ids: [...], category_id?, recurring?, note?}"""
    data = request.json or {}
    ids = data.get("ids") or []
    fields = [f for f in ("category_id", "recurring", "note") if f in data]
    if not ids or not fields:
        return error("Rien à modifier")
    with connect() as conn:
        conn.execute(
            f"UPDATE transactions SET {', '.join(f + '=?' for f in fields)} "
            f"WHERE id IN ({','.join('?' * len(ids))})",
            [data[f] for f in fields] + ids,
        )
    return jsonify({"ok": True})


@app.delete("/api/transactions")
def delete_transactions():
    ids = (request.json or {}).get("ids") or []
    if ids:
        with connect() as conn:
            conn.execute(f"DELETE FROM transactions WHERE id IN ({','.join('?' * len(ids))})", ids)
    return jsonify({"ok": True})


def _tx_fields(d: dict) -> dict | None:
    """Valide les champs d'une opération saisie ou modifiée à la main ; None si invalide."""
    date_iso = importer.parse_date(str(d.get("date") or ""))
    amount = importer.parse_amount(str(d.get("amount", "")))
    label = (d.get("label") or "").strip()
    if not date_iso or amount is None or not label or not d.get("account_id"):
        return None
    return {
        "account_id": int(d["account_id"]), "date": date_iso, "label": label, "amount": round(amount, 2),
        "category_id": d.get("category_id") or None, "recurring": int(bool(d.get("recurring"))),
        "note": (d.get("note") or "").strip(),
    }


@app.post("/api/transactions")
def create_transaction():
    """Saisie manuelle d'une opération (ex : dépense en espèces)."""
    tx = _tx_fields(request.json or {})
    if tx is None:
        return error("Compte, date, libellé et montant sont obligatoires")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO transactions(account_id, date, label, amount, category_id, recurring, note, hash) "
            "VALUES (:account_id, :date, :label, :amount, :category_id, :recurring, :note, :hash)",
            {**tx, "hash": "manual-" + uuid.uuid4().hex},
        )
    return jsonify({"id": cur.lastrowid})


@app.put("/api/transactions/<int:tx_id>")
def update_transaction(tx_id):
    """Modification complète d'une opération (date, libellé, montant, compte…).
    L'empreinte `hash` est volontairement conservée : en réimportant le même relevé, la ligne
    d'origine est reconnue comme déjà présente et la version corrigée n'est pas dupliquée."""
    tx = _tx_fields(request.json or {})
    if tx is None:
        return error("Compte, date, libellé et montant sont obligatoires")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE transactions SET account_id=:account_id, date=:date, label=:label, amount=:amount, "
            "category_id=:category_id, recurring=:recurring, note=:note WHERE id=:id",
            {**tx, "id": tx_id},
        )
    if not cur.rowcount:
        return error("Opération introuvable", 404)
    return jsonify({"ok": True})


@app.post("/api/recurring/detect")
def detect_recurring():
    """Marque comme récurrentes les dépenses dont le libellé (normalisé) revient
    sur au moins 3 mois différents, environ une fois par mois, avec un montant comparable (±15 %)."""
    with connect() as conn:
        txs = conn.execute("SELECT id, label, amount, date FROM transactions WHERE amount < 0").fetchall()
        groups = defaultdict(list)
        for t in txs:
            key = importer.normalize_label(t["label"])
            if key:
                groups[key].append(t)
        to_mark = []
        for items in groups.values():
            months = {t["date"][:7] for t in items}
            if len(months) < 3:
                continue
            amounts = sorted(abs(t["amount"]) for t in items)
            median = amounts[len(amounts) // 2]
            similar = [t for t in items if abs(abs(t["amount"]) - median) <= 0.15 * median]
            similar_months = {t["date"][:7] for t in similar}
            # ~1 opération par mois (abonnement, facture) et non des achats fréquents (courses…)
            if (len(similar_months) >= 3 and len(items) <= 1.3 * len(months)
                    and len(similar_months) >= 0.6 * len(months)):
                to_mark += [t["id"] for t in similar]
        if to_mark:
            conn.execute(
                f"UPDATE transactions SET recurring=1 WHERE recurring=0 AND id IN ({','.join('?' * len(to_mark))})",
                to_mark,
            )
        return jsonify({"marked": conn.total_changes})


# ---------------------------------------------------------------- Import CSV
def _read_upload():
    f = request.files.get("file")
    if not f:
        raise ValueError("Aucun fichier reçu")
    header, body, delim = importer.read_rows(importer.decode(f.read()))
    if not header:
        raise ValueError("Fichier vide ou illisible")
    return header, body, delim


@app.post("/api/import/preview")
def import_preview():
    try:
        header, body, delim = _read_upload()
    except ValueError as e:
        return error(str(e))
    return jsonify({
        "header": header, "rows": body[:8], "count": len(body), "delimiter": delim,
        "mapping": importer.guess_mapping(header, body),
    })


@app.post("/api/import/commit")
def import_commit():
    try:
        header, body, _ = _read_upload()
    except ValueError as e:
        return error(str(e))
    account_id = int(request.form["account_id"])
    mapping = json.loads(request.form["mapping"])
    invert = request.form.get("invert") == "1"
    txs, errors = importer.parse_transactions(header, body, mapping)
    inserted_ids, seen = [], defaultdict(int)
    with connect() as conn:
        for tx in txs:
            if invert:
                tx["amount"] = -tx["amount"]
            base = (tx["date"], tx["label"], tx["amount"])
            seen[base] += 1
            cur = conn.execute(
                "INSERT OR IGNORE INTO transactions(account_id, date, label, amount, hash) VALUES (?,?,?,?,?)",
                (account_id, tx["date"], tx["label"], tx["amount"], importer.tx_hash(account_id, tx, seen[base])),
            )
            if cur.rowcount:
                inserted_ids.append(cur.lastrowid)
        categorized = apply_rules(conn, only_uncategorized=True, tx_ids=inserted_ids)
    return jsonify({
        "inserted": len(inserted_ids), "duplicates": len(txs) - len(inserted_ids),
        "categorized": categorized, "errors": errors[:20], "error_count": len(errors),
    })


# ---------------------------------------------------------------- Statistiques
@app.get("/api/months")
def months():
    with connect() as conn:
        return jsonify([r[0] for r in conn.execute(
            "SELECT DISTINCT substr(date, 1, 7) FROM transactions ORDER BY 1 DESC")])


def month_range(end: str, count: int) -> list[str]:
    y, m = map(int, end.split("-"))
    out = []
    for _ in range(count):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


@app.get("/api/stats")
def stats():
    end = request.args.get("end") or date.today().strftime("%Y-%m")
    count = max(1, min(int(request.args.get("months", 12)), 60))
    months_list = month_range(end, count)
    cond, params = ["substr(t.date, 1, 7) BETWEEN ? AND ?"], [months_list[0], months_list[-1]]
    if request.args.get("account"):
        cond.append("t.account_id = ?")
        params.append(request.args["account"])
    where = " AND ".join(cond)
    idx = {m: i for i, m in enumerate(months_list)}

    with connect() as conn:
        data = conn.execute(f"""
            SELECT substr(t.date, 1, 7) AS month, {KIND_SQL} AS kind, t.recurring,
                   COALESCE(c.name, 'Non catégorisé') AS category, COALESCE(c.color, '#cbd5e1') AS color,
                   SUM(t.amount) AS total
            FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
            WHERE {where}
            GROUP BY month, kind, t.recurring, category""", params).fetchall()

    zeros = lambda: [0.0] * count  # noqa: E731
    by_cat, colors = defaultdict(zeros), {}
    income, expense, recurring, one_off = zeros(), zeros(), zeros(), zeros()
    for r in data:
        i = idx[r["month"]]
        if r["kind"] == "expense":
            spent = -r["total"]  # les remboursements (montants positifs) viennent en déduction
            by_cat[r["category"]][i] += spent
            colors[r["category"]] = r["color"]
            expense[i] += spent
            (recurring if r["recurring"] else one_off)[i] += spent
        elif r["kind"] == "income":
            income[i] += r["total"]

    r2 = lambda xs: [round(x, 2) for x in xs]  # noqa: E731
    series = sorted(
        ({"category": k, "color": colors[k], "values": r2(v)} for k, v in by_cat.items()),
        key=lambda s: -sum(s["values"]),
    )
    return jsonify({
        "months": months_list, "categories": series,
        "income": r2(income), "expense": r2(expense),
        "recurring": r2(recurring), "one_off": r2(one_off),
    })


if __name__ == "__main__":
    init_db()
    port = 5050
    Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False)
