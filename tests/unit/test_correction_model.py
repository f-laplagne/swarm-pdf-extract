from domain.models import Correction, CorrectionStatut

def test_correction_cree_avec_statut_par_defaut():
    c = Correction(
        ligne_id=1,
        champ="type_matiere",
        valeur_originale="sble",
        valeur_corrigee="Sable",
        confiance_originale=0.45,
        corrige_par="admin",
    )
    assert c.statut == CorrectionStatut.APPLIQUEE
    assert c.notes is None
    assert c.id is None

def test_correction_statut_enum_valeurs():
    assert CorrectionStatut.APPLIQUEE.value == "appliquee"
    assert CorrectionStatut.REJETEE.value == "rejetee"
