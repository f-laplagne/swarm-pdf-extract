import json
import glob
import os
from datetime import date, datetime
from sqlalchemy.orm import Session

from dashboard.data.models import Fournisseur, Document, LigneFacture


def _parse_date(s: str | None) -> str | None:
    """Keep ISO date strings as-is, return None for empty/null."""
    if not s:
        return None
    return s


def _parse_date_obj(s: str | None) -> date | None:
    """Parse ISO date string to Python date object."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _get_or_create_fournisseur(session: Session, fournisseur_data: dict | None) -> Fournisseur | None:
    if not fournisseur_data or not fournisseur_data.get("nom"):
        return None

    nom = fournisseur_data["nom"]
    existing = session.query(Fournisseur).filter_by(nom=nom).first()
    if existing:
        return existing

    f = Fournisseur(
        nom=nom,
        adresse=fournisseur_data.get("adresse"),
        siret=fournisseur_data.get("siret"),
        tva_intra=fournisseur_data.get("tva_intra"),
    )
    session.add(f)
    session.flush()
    return f


def ingest_extraction_json(session: Session, data: dict) -> Document | None:
    """Ingest a single extraction JSON dict into the database.
    Returns the Document or None if skipped (duplicate)."""

    fichier = data["fichier"]

    # Skip if already ingested
    existing = session.query(Document).filter_by(fichier=fichier).first()
    if existing:
        return None

    meta = data.get("metadonnees", {})
    refs = meta.get("references", {}) or {}

    fournisseur = _get_or_create_fournisseur(session, meta.get("fournisseur"))

    client = meta.get("client", {}) or {}

    doc = Document(
        fichier=fichier,
        type_document=data.get("type_document"),
        format_pdf=None,  # from classification, not extraction
        fournisseur_id=fournisseur.id if fournisseur else None,
        client_nom=client.get("nom"),
        client_adresse=client.get("adresse"),
        date_document=_parse_date_obj(meta.get("date_document")),
        numero_document=meta.get("numero_document"),
        montant_ht=meta.get("montant_ht"),
        montant_tva=meta.get("montant_tva"),
        montant_ttc=meta.get("montant_ttc"),
        devise=meta.get("devise", "EUR"),
        conditions_paiement=meta.get("conditions_paiement"),
        ref_commande=refs.get("commande"),
        ref_contrat=refs.get("contrat"),
        ref_bon_livraison=refs.get("bon_livraison"),
        confiance_globale=data.get("confiance_globale"),
        strategie_utilisee=data.get("strategie_utilisee"),
    )
    session.add(doc)
    session.flush()

    for ligne_data in data.get("lignes", []):
        conf = ligne_data.get("confiance", {})
        ligne = LigneFacture(
            document_id=doc.id,
            ligne_numero=ligne_data.get("ligne_numero"),
            type_matiere=ligne_data.get("type_matiere"),
            unite=ligne_data.get("unite"),
            prix_unitaire=ligne_data.get("prix_unitaire"),
            quantite=ligne_data.get("quantite"),
            prix_total=ligne_data.get("prix_total"),
            date_depart=_parse_date(ligne_data.get("date_depart")),
            date_arrivee=_parse_date(ligne_data.get("date_arrivee")),
            lieu_depart=ligne_data.get("lieu_depart"),
            lieu_arrivee=ligne_data.get("lieu_arrivee"),
            conf_type_matiere=conf.get("type_matiere"),
            conf_unite=conf.get("unite"),
            conf_prix_unitaire=conf.get("prix_unitaire"),
            conf_quantite=conf.get("quantite"),
            conf_prix_total=conf.get("prix_total"),
            conf_date_depart=conf.get("date_depart"),
            conf_date_arrivee=conf.get("date_arrivee"),
            conf_lieu_depart=conf.get("lieu_depart"),
            conf_lieu_arrivee=conf.get("lieu_arrivee"),
        )
        session.add(ligne)

    return doc


def ingest_directory(session: Session, directory: str) -> dict:
    """Ingest all *_extraction.json files from a directory.
    Returns stats dict with ingested/skipped/errors counts."""

    stats = {"ingested": 0, "skipped": 0, "errors": 0, "files": []}

    pattern = os.path.join(directory, "*_extraction.json")
    for filepath in sorted(glob.glob(pattern)):
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            result = ingest_extraction_json(session, data)
            if result is None:
                stats["skipped"] += 1
                stats["files"].append({"file": filename, "status": "skipped"})
            else:
                stats["ingested"] += 1
                stats["files"].append({"file": filename, "status": "ingested"})

        except Exception as e:
            stats["errors"] += 1
            stats["files"].append({"file": filename, "status": "error", "error": str(e)})

    session.commit()
    return stats
