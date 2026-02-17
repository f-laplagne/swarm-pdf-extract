"""Domain purchasing analytics — pure functions, zero external dependencies.

Only stdlib and domain.models imports allowed.
"""

from domain.models import ClassementFournisseur, LigneFacture


def weighted_average_price(items):
    """Compute weighted average price from (price, quantity) pairs."""
    total_qty = sum(qty for _, qty in items)
    if total_qty == 0:
        return 0.0
    return sum(price * qty for price, qty in items) / total_qty


def rank_suppliers_by_amount(lines, limit=5):
    """Rank suppliers by total amount from (LigneFacture, fournisseur_name) pairs."""
    by_supplier = {}
    for ligne, fournisseur in lines:
        if fournisseur not in by_supplier:
            by_supplier[fournisseur] = {"montant": 0.0, "count": 0}
        by_supplier[fournisseur]["montant"] += ligne.prix_total or 0
        by_supplier[fournisseur]["count"] += 1
    ranked = [
        ClassementFournisseur(
            nom=name,
            montant_total=data["montant"],
            nombre_documents=data["count"],
        )
        for name, data in by_supplier.items()
    ]
    ranked.sort(key=lambda s: s.montant_total, reverse=True)
    return ranked[:limit]


def fragmentation_index(lines):
    """Compute fragmentation: how many suppliers per material type."""
    by_material = {}
    for ligne, fournisseur in lines:
        mat = ligne.type_matiere or "inconnu"
        by_material.setdefault(mat, set()).add(fournisseur)
    return {mat: len(suppliers) for mat, suppliers in by_material.items()}
