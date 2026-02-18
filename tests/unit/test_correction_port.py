from domain.ports import CorrectionPort
from domain.models import Correction, CorrectionStatut


class FakeCorrectionRepository(CorrectionPort):
    def __init__(self):
        self._store: list[Correction] = []

    def sauvegarder(self, correction: Correction) -> Correction:
        correction.id = len(self._store) + 1
        self._store.append(correction)
        return correction

    def historique(self, champ: str, valeur_originale: str) -> list[Correction]:
        return [
            c for c in self._store
            if c.champ == champ and c.valeur_originale == valeur_originale
        ]


def test_correction_port_peut_sauvegarder_et_lire():
    repo = FakeCorrectionRepository()
    c = Correction(
        ligne_id=1, champ="type_matiere",
        valeur_originale="sble", valeur_corrigee="Sable",
        confiance_originale=0.45, corrige_par="admin",
    )
    saved = repo.sauvegarder(c)
    assert saved.id == 1
    history = repo.historique("type_matiere", "sble")
    assert len(history) == 1
    assert history[0].valeur_corrigee == "Sable"
