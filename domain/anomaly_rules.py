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


def check_date_order(ligne):
    """Check that date_arrivee is not before date_depart."""
    if not ligne.date_depart or not ligne.date_arrivee:
        return ResultatAnomalie(
            est_valide=True,
            code_regle="DATE_001",
            description="Dates manquantes",
        )
    if ligne.date_arrivee < ligne.date_depart:
        return ResultatAnomalie(
            est_valide=False,
            code_regle="DATE_001",
            description="Date d'arrivee anterieure au depart",
            details={
                "depart": str(ligne.date_depart),
                "arrivee": str(ligne.date_arrivee),
            },
        )
    return ResultatAnomalie(
        est_valide=True,
        code_regle="DATE_001",
        description="Dates coherentes",
    )


def check_low_confidence(confiance_globale, seuil=0.6):
    """Check that global confidence is above threshold."""
    if confiance_globale < seuil:
        return ResultatAnomalie(
            est_valide=False,
            code_regle="CONF_001",
            description=f"Confiance {confiance_globale:.2f} < seuil {seuil}",
            details={"confiance": confiance_globale, "seuil": seuil},
        )
    return ResultatAnomalie(
        est_valide=True,
        code_regle="CONF_001",
        description="Confiance suffisante",
    )
