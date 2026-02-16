"""Entity Management Page -- manage entity mappings, merges, audit log, and reviews."""

import json

import pandas as pd
import streamlit as st
from sqlalchemy import select, union_all

from dashboard.data.db import get_session
from dashboard.data.models import (
    Document,
    EntityMapping,
    Fournisseur,
    LigneFacture,
    MergeAuditLog,
)
from dashboard.data.entity_resolution import (
    get_reverse_mappings,
    merge_entities,
    revert_merge,
    get_pending_reviews,
)
from dashboard.data.entity_enrichment import run_auto_resolution

st.set_page_config(page_title="Gestion des entites", page_icon="\U0001f517", layout="wide")
st.title("\U0001f517 Gestion des entites")

engine = st.session_state.get("engine")
if not engine:
    from dashboard.data.db import get_engine, init_db

    engine = get_engine()
    init_db(engine)

session = get_session(engine)
config = st.session_state.get("config", {})

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTITY_TYPES = {
    "Lieux": "location",
    "Matieres": "material",
    "Fournisseurs": "supplier",
    "Societes": "company",
}

ENTITY_LABELS = {v: k for k, v in ENTITY_TYPES.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_raw_values(entity_type: str) -> list[str]:
    """Return sorted distinct *raw* values from the source tables and EntityMapping.

    Unlike ``get_distinct_values`` which resolves to canonical names, this
    returns the unprocessed values that appear in the data -- useful for the
    manual merge multiselect.
    """
    queries = {
        "location": lambda: union_all(
            select(LigneFacture.lieu_depart.label("val")).where(
                LigneFacture.lieu_depart.isnot(None)
            ),
            select(LigneFacture.lieu_arrivee.label("val")).where(
                LigneFacture.lieu_arrivee.isnot(None)
            ),
        ),
        "material": lambda: select(LigneFacture.type_matiere.label("val")).where(
            LigneFacture.type_matiere.isnot(None)
        ),
        "supplier": lambda: select(Fournisseur.nom.label("val")).where(
            Fournisseur.nom.isnot(None)
        ),
        "company": lambda: select(Document.client_nom.label("val")).where(
            Document.client_nom.isnot(None)
        ),
    }

    factory = queries.get(entity_type)
    raw_set: set[str] = set()

    if factory is not None:
        subq = factory().subquery()
        for row in session.execute(select(subq.c.val).distinct()):
            if row.val is not None and str(row.val).strip():
                raw_set.add(str(row.val))

    # Also include raw_values already registered in EntityMapping
    em_stmt = (
        select(EntityMapping.raw_value)
        .where(EntityMapping.entity_type == entity_type)
        .distinct()
    )
    for row in session.execute(em_stmt):
        if row.raw_value and str(row.raw_value).strip():
            raw_set.add(str(row.raw_value))

    return sorted(raw_set)


# ---------------------------------------------------------------------------
# Auto-resolution
# ---------------------------------------------------------------------------

st.subheader("Resolution automatique")

col_auto1, col_auto2 = st.columns([1, 3])
with col_auto1:
    if st.button("Lancer la resolution automatique", key="btn_auto_resolve", type="primary"):
        auto_config = config if config.get("entity_resolution") else {
            "entity_resolution": {
                "auto_merge_threshold": 0.90,
                "review_threshold": 0.50,
                "fuzzy_min_score": 50,
            }
        }
        with st.spinner("Resolution en cours..."):
            stats = run_auto_resolution(session, auto_config)
        st.session_state["auto_resolution_stats"] = stats
        st.rerun()

with col_auto2:
    if "auto_resolution_stats" in st.session_state:
        stats = st.session_state["auto_resolution_stats"]
        st.success(
            f"Resolution terminee : **{stats['auto_merged']}** fusion(s) automatique(s), "
            f"**{stats['pending_review']}** en attente de revue, "
            f"**{stats['ignored']}** ignore(s)."
        )

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_mappings, tab_merge, tab_audit, tab_review = st.tabs(
    ["Mappings actuels", "Fusion manuelle", "Journal d'audit", "Revue en attente"]
)

# ============================================================
# Tab 1: Mappings actuels (Current Mappings)
# ============================================================
with tab_mappings:
    st.subheader("Mappings approuves")

    selected_label = st.radio(
        "Type d'entite",
        list(ENTITY_TYPES.keys()),
        horizontal=True,
        key="tab1_entity_type",
    )
    selected_type = ENTITY_TYPES[selected_label]

    reverse = get_reverse_mappings(session, selected_type)

    if reverse:
        rows = []
        for canonical, raw_list in sorted(reverse.items()):
            # Also fetch metadata from one representative mapping row
            rep_stmt = (
                select(EntityMapping)
                .where(EntityMapping.entity_type == selected_type)
                .where(EntityMapping.canonical_value == canonical)
                .where(EntityMapping.status == "approved")
                .limit(1)
            )
            rep = session.execute(rep_stmt).scalar_one_or_none()
            rows.append(
                {
                    "canonical_value": canonical,
                    "raw_values": ", ".join(sorted(raw_list)),
                    "source": rep.source if rep else "",
                    "confidence": rep.confidence if rep else None,
                    "created_at": (
                        rep.created_at.strftime("%Y-%m-%d %H:%M") if rep and rep.created_at else ""
                    ),
                }
            )

        df_mappings = pd.DataFrame(rows)
        st.dataframe(df_mappings, use_container_width=True, hide_index=True)

        # Delete per canonical group
        st.markdown("#### Supprimer un mapping")
        canonical_to_delete = st.selectbox(
            "Valeur canonique a supprimer",
            options=[""] + sorted(reverse.keys()),
            key="delete_canonical_select",
        )
        if canonical_to_delete and st.button(
            f"Supprimer tous les mappings pour '{canonical_to_delete}'",
            key="btn_delete_mapping",
        ):
            del_stmt = (
                select(EntityMapping)
                .where(EntityMapping.entity_type == selected_type)
                .where(EntityMapping.canonical_value == canonical_to_delete)
                .where(EntityMapping.status == "approved")
            )
            to_delete = list(session.scalars(del_stmt))
            for m in to_delete:
                session.delete(m)
            session.commit()
            st.success(
                f"{len(to_delete)} mapping(s) supprime(s) pour '{canonical_to_delete}'."
            )
            st.rerun()
    else:
        st.info("Aucun mapping approuve pour ce type d'entite.")


# ============================================================
# Tab 2: Fusion manuelle (Manual Merge)
# ============================================================
with tab_merge:
    st.subheader("Fusionner des entites")

    merge_label = st.radio(
        "Type d'entite",
        list(ENTITY_TYPES.keys()),
        horizontal=True,
        key="tab2_entity_type",
    )
    merge_type = ENTITY_TYPES[merge_label]

    all_raw = _get_raw_values(merge_type)

    if all_raw:
        selected_values = st.multiselect(
            "Selectionner 2+ valeurs a fusionner",
            options=all_raw,
            key="merge_multiselect",
        )

        default_canonical = selected_values[0] if selected_values else ""
        canonical_name = st.text_input(
            "Nom canonique",
            value=default_canonical,
            key="merge_canonical_input",
        )

        match_mode = st.radio(
            "Mode de correspondance",
            ["Exact", "Prefix"],
            horizontal=True,
            key="merge_match_mode",
            help="Prefix : les valeurs commencant par la valeur brute seront resolues vers le canonique.",
        )
        match_mode_val = "exact" if match_mode == "Exact" else "prefix"

        notes = st.text_area(
            "Notes (optionnel)",
            key="merge_notes",
            height=80,
        )

        can_merge = len(selected_values) >= 2 and canonical_name.strip()

        if can_merge:
            if st.button("Fusionner", key="btn_merge", type="primary"):
                try:
                    audit = merge_entities(
                        session=session,
                        entity_type=merge_type,
                        canonical=canonical_name.strip(),
                        raw_values=selected_values,
                        match_mode=match_mode_val,
                        source="manual",
                        confidence=1.0,
                        performed_by="admin",
                        notes=notes.strip() or None,
                    )
                    st.success(
                        f"Fusion reussie ! {len(selected_values)} valeurs fusionnees "
                        f"vers '{canonical_name.strip()}' (audit #{audit.id})."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erreur lors de la fusion : {exc}")
        else:
            st.info("Selectionnez au moins 2 valeurs et saisissez un nom canonique.")
    else:
        st.info("Aucune valeur brute trouvee pour ce type d'entite.")


# ============================================================
# Tab 3: Journal d'audit (Audit Log)
# ============================================================
with tab_audit:
    st.subheader("Journal d'audit des fusions")

    # Filters
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        audit_type_filter = st.selectbox(
            "Filtrer par type d'entite",
            options=["Tous"] + list(ENTITY_TYPES.keys()),
            key="audit_type_filter",
        )
    with col_f2:
        audit_action_filter = st.selectbox(
            "Filtrer par action",
            options=["Toutes", "merge", "revert"],
            key="audit_action_filter",
        )

    audit_stmt = select(MergeAuditLog).order_by(MergeAuditLog.performed_at.desc())

    if audit_type_filter != "Tous":
        audit_stmt = audit_stmt.where(
            MergeAuditLog.entity_type == ENTITY_TYPES[audit_type_filter]
        )
    if audit_action_filter != "Toutes":
        audit_stmt = audit_stmt.where(MergeAuditLog.action == audit_action_filter)

    audit_entries = list(session.scalars(audit_stmt))

    if audit_entries:
        audit_rows = []
        for entry in audit_entries:
            try:
                raw_vals = json.loads(entry.raw_values_json)
            except (json.JSONDecodeError, TypeError):
                raw_vals = []
            audit_rows.append(
                {
                    "ID": entry.id,
                    "Action": entry.action,
                    "Type": ENTITY_LABELS.get(entry.entity_type, entry.entity_type),
                    "Valeur canonique": entry.canonical_value,
                    "Valeurs brutes": ", ".join(raw_vals) if raw_vals else "",
                    "Par": entry.performed_by or "",
                    "Date": (
                        entry.performed_at.strftime("%Y-%m-%d %H:%M")
                        if entry.performed_at
                        else ""
                    ),
                    "Notes": entry.notes or "",
                    "Annule": "Oui" if entry.reverted else "Non",
                }
            )

        df_audit = pd.DataFrame(audit_rows)
        st.dataframe(df_audit, use_container_width=True, hide_index=True)

        # Revert controls
        non_reverted = [e for e in audit_entries if not e.reverted and e.action == "merge"]
        if non_reverted:
            st.markdown("#### Annuler une fusion")
            revert_options = {
                f"#{e.id} - {e.canonical_value} ({ENTITY_LABELS.get(e.entity_type, e.entity_type)})": e.id
                for e in non_reverted
            }
            revert_selection = st.selectbox(
                "Fusion a annuler",
                options=[""] + list(revert_options.keys()),
                key="revert_select",
            )
            if revert_selection and st.button("Annuler cette fusion", key="btn_revert"):
                audit_id = revert_options[revert_selection]
                success = revert_merge(session, audit_id, performed_by="admin")
                if success:
                    st.success(f"Fusion #{audit_id} annulee avec succes.")
                    st.rerun()
                else:
                    st.error(
                        "Impossible d'annuler cette fusion (deja annulee ou introuvable)."
                    )
    else:
        st.info("Aucune entree dans le journal d'audit.")


# ============================================================
# Tab 4: Revue en attente (Pending Review)
# ============================================================
with tab_review:
    st.subheader("Mappings en attente de revue")

    pending = get_pending_reviews(session)

    if pending:
        # Bulk actions
        col_bulk1, col_bulk2, _ = st.columns([1, 1, 4])
        with col_bulk1:
            if st.button("Tout approuver", key="btn_bulk_approve", type="primary"):
                for m in pending:
                    m.status = "approved"
                session.commit()
                st.success(f"{len(pending)} mapping(s) approuve(s).")
                st.rerun()
        with col_bulk2:
            if st.button("Tout rejeter", key="btn_bulk_reject"):
                for m in pending:
                    m.status = "rejected"
                session.commit()
                st.success(f"{len(pending)} mapping(s) rejete(s).")
                st.rerun()

        # Individual rows
        for m in pending:
            with st.container():
                cols = st.columns([2, 2, 1, 1, 1, 1])
                with cols[0]:
                    st.text(f"Brut: {m.raw_value}")
                with cols[1]:
                    st.text(f"Canonique: {m.canonical_value}")
                with cols[2]:
                    st.text(f"Conf: {m.confidence:.0%}" if m.confidence else "Conf: -")
                with cols[3]:
                    st.text(f"Source: {m.source or '-'}")
                with cols[4]:
                    if st.button("Approuver", key=f"approve_{m.id}"):
                        m.status = "approved"
                        session.commit()
                        st.rerun()
                with cols[5]:
                    if st.button("Rejeter", key=f"reject_{m.id}"):
                        m.status = "rejected"
                        session.commit()
                        st.rerun()
                st.divider()
    else:
        st.info("Aucun mapping en attente de revue.")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
session.close()
