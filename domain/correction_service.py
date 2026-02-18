"""Domain service for correction logic — pure Python, zero external dependencies."""

from __future__ import annotations

from collections import Counter

from domain.models import Correction


class CorrectionService:
    """Pure domain logic for correction suggestion and propagation decisions."""

    @staticmethod
    def suggerer(
        champ: str,
        valeur_originale: str,
        historique: list[Correction],
    ) -> str | None:
        """Return the most frequent correction applied to this (champ, valeur_originale) pair.

        Returns None if no relevant history exists.
        """
        candidats = [
            c.valeur_corrigee
            for c in historique
            if c.champ == champ and c.valeur_originale == valeur_originale
        ]
        if not candidats:
            return None
        counter = Counter(candidats)
        return counter.most_common(1)[0][0]

    @staticmethod
    def lignes_a_propager(
        champ: str,
        valeur_originale: str,
        lignes: list,
        conf_par_ligne: dict[int, float | None],
        seuil: float = 0.70,
    ) -> list:
        """Return lines eligible for bulk propagation of a correction.

        A line is eligible if its field value equals valeur_originale
        AND its confidence for that field is below seuil (or unknown).

        Args:
            champ: The field name to check (e.g. "type_matiere").
            valeur_originale: The raw value that was corrected.
            lignes: Candidate objects with .ligne_numero and field attributes.
            conf_par_ligne: Map of ligne.ligne_numero -> confidence score.
            seuil: Confidence threshold below which propagation is applied.
        """
        eligible = []
        for ligne in lignes:
            valeur_actuelle = getattr(ligne, champ, None)
            if valeur_actuelle != valeur_originale:
                continue
            conf = conf_par_ligne.get(ligne.ligne_numero)
            if conf is None or conf < seuil:
                eligible.append(ligne)
        return eligible
