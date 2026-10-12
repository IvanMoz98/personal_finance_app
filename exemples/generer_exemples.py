"""Génère deux relevés CSV fictifs (formats différents) pour tester l'application."""
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(4)
here = Path(__file__).parent
start = date(2025, 10, 1)
months = [(start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1) for i in range(13)]

ops = []
for y, m in months:
    ops += [
        (date(y, m, 1), "PRLV SEPA LOYER SCI DES TILLEULS", -850.00),
        (date(y, m, 3), "PRLV SEPA EDF CLIENTS PARTICULIERS", -round(random.uniform(60, 95), 2)),
        (date(y, m, 5), "PRLV SEPA FREE MOBILE", -15.99),
        (date(y, m, 8), "CB NETFLIX.COM", -13.49),
        (date(y, m, 27), "VIR SALAIRE ACME SAS", 2650.00),
        (date(y, m, 10), "VIR VERS LIVRET A", -200.00),
    ]
    for _ in range(random.randint(5, 8)):
        shop = random.choice(["CARREFOUR MARKET", "LIDL", "BIOCOOP", "MONOPRIX"])
        ops.append((date(y, m, random.randint(1, 28)), f"CB {shop} {random.randint(10,99)}/{m:02d}", -round(random.uniform(12, 110), 2)))
    for _ in range(random.randint(2, 5)):
        lbl = random.choice(["CB RESTAURANT LE BISTROT", "CB UBER EATS", "CB TOTALENERGIES", "CB SNCF CONNECT", "CB FNAC", "CB CINEMA PATHE", "CB PHARMACIE CENTRALE"])
        ops.append((date(y, m, random.randint(1, 28)), lbl, -round(random.uniform(8, 90), 2)))
ops.sort()

# Format 1 : préambule, point-virgule, Débit/Crédit séparés, encodage Windows
lines = ["Compte courant n° 12345678901;;;", "Solde au 11/10/2026;3 512,40 €;;", "", "Date;Libellé;Débit euros;Crédit euros;"]
for d, l, a in ops:
    deb = f"{-a:.2f}".replace(".", ",") if a < 0 else ""
    cre = f"{a:.2f}".replace(".", ",") if a > 0 else ""
    lines.append(f"{d:%d/%m/%Y};{l};{deb};{cre};")
(here / "releve_banque_A.csv").write_bytes("\r\n".join(lines).encode("cp1252"))

# Format 2 : virgule, montant signé, dates ISO (carte d'une autre banque)
rows = ["date,description,amount"]
d = start
while d < date(2026, 10, 31):
    rows.append(f"{d.isoformat()},AMAZON MARKETPLACE,-{random.uniform(10, 60):.2f}")
    if d.month in (12, 7):
        rows.append(f"{d.isoformat()},AIR FRANCE BILLETS,-{random.uniform(200, 450):.2f}")
    d += timedelta(days=random.randint(9, 20))
(here / "releve_banque_B.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
print("Fichiers générés dans", here)
