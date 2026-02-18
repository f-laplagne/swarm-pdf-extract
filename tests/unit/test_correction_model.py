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


def test_correction_avec_statut_rejete():
    c = Correction(
        ligne_id=1,
        champ="prix_unitaire",
        valeur_originale="10.5",
        valeur_corrigee="10.50",
        confiance_originale=0.8,
        corrige_par="reviewer",
        statut=CorrectionStatut.REJETEE,
    )
    assert c.statut == CorrectionStatut.REJETEE


def test_correction_avec_optionnels_renseignes():
    from datetime import datetime
    now = datetime.now()
    c = Correction(
        ligne_id=2,
        champ="lieu_depart",
        valeur_originale="Marseile",
        valeur_corrigee="Marseille",
        confiance_originale=0.3,
        corrige_par="user123",
        notes="Correction orthographe",
        timestamp=now,
        id=42,
    )
    assert c.notes == "Correction orthographe"
    assert c.timestamp == now
    assert c.id == 42
