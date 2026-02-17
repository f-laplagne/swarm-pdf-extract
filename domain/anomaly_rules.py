"""Domain anomaly rules — pure functions, zero external dependencies.

Only stdlib and domain.models imports allowed.
"""

from domain.models import LigneFacture, ResultatAnomalie


def check_calculation_coherence(ligne, tolerance=0.01):
    """Check that prix_unitaire * quantite matches prix_total within tolerance."""
    if not all([ligne.prix_unitaire, ligne.quantite, ligne.prix_total]):
        return ResultatAnomalie(
            est_valide=True,
            code_regle="CALC_001",
            description="Champs manquants, verification impossible",
        )
    attendu = ligne.prix_unitaire * ligne.quantite
    ecart = abs(attendu - ligne.prix_total) / abs(ligne.prix_total)
    if ecart > tolerance:
        return ResultatAnomalie(
            est_valide=False,
            code_regle="CALC_001",
            description=f"Ecart de {ecart:.1%} entre calcul et total",
            details={
                "attendu": attendu,
                "reel": ligne.prix_total,
                "ecart_pct": ecart,
            },
        )
    return ResultatAnomalie(
        est_valide=True,
        code_regle="CALC_001",
        description="Calcul coherent",
    )
