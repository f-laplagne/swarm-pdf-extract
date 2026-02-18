from domain.correction_service import CorrectionService
from domain.models import Correction


def _make_correction(valeur_corrigee: str, n: int = 1) -> list[Correction]:
    return [
        Correction(
            ligne_id=i, champ="type_matiere",
            valeur_originale="sble", valeur_corrigee=valeur_corrigee,
            confiance_originale=0.4, corrige_par="admin",
        )
        for i in range(n)
    ]


def test_suggerer_retourne_valeur_la_plus_frequente():
    historique = (
        _make_correction("Sable", 3)
        + _make_correction("SABLE", 1)
    )
    suggestion = CorrectionService.suggerer("type_matiere", "sble", historique)
    assert suggestion == "Sable"


def test_suggerer_retourne_none_si_historique_vide():
    suggestion = CorrectionService.suggerer("type_matiere", "xyz", [])
    assert suggestion is None


def test_suggerer_retourne_none_si_aucune_correction_pour_ce_champ():
    historique = _make_correction("Sable", 2)
    suggestion = CorrectionService.suggerer("unite", "sble", historique)
    assert suggestion is None


def test_lignes_a_propager_retourne_lignes_eligibles():
    """Lines with same raw value and low confidence are eligible for propagation."""

    class _FakeLigne:
        def __init__(self, numero, valeur):
            self.ligne_numero = numero
            self.type_matiere = valeur

    lignes = [
        _FakeLigne(1, "sble"),
        _FakeLigne(2, "sble"),
        _FakeLigne(3, "Sable"),  # already correct value — excluded
    ]
    conf_map = {1: 0.45, 2: 0.30, 3: 1.0}
    result = CorrectionService.lignes_a_propager(
        champ="type_matiere",
        valeur_originale="sble",
        lignes=lignes,
        conf_par_ligne=conf_map,
        seuil=0.70,
    )
    numeros = [l.ligne_numero for l in result]
    assert 1 in numeros
    assert 2 in numeros
    assert 3 not in numeros


def test_lignes_a_propager_exclut_lignes_confiance_haute():

    class _FakeLigne:
        def __init__(self, numero, valeur):
            self.ligne_numero = numero
            self.type_matiere = valeur

    lignes = [_FakeLigne(1, "sble")]
    conf_map = {1: 0.95}  # high confidence — skip
    result = CorrectionService.lignes_a_propager(
        champ="type_matiere", valeur_originale="sble",
        lignes=lignes, conf_par_ligne=conf_map, seuil=0.70,
    )
    assert result == []
