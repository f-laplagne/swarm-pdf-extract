import hashlib
import streamlit as st
import os
import pandas as pd
from dashboard.data.db import get_session, init_db
from dashboard.data.ingestion import ingest_directory
from dashboard.data.models import Document, LigneFacture, Fournisseur, Anomalie, UploadLog
from dashboard.data.upload_pipeline import save_upload, check_duplicate, create_upload_record
from sqlalchemy import func

st.set_page_config(page_title="Administration", page_icon="\u2699\uFE0F", layout="wide")
from dashboard.styles.theme import inject_theme
inject_theme()

st.title("\u2699\uFE0F Administration")

engine = st.session_state.get("engine")
config = st.session_state.get("config", {})
if not engine:
    from dashboard.data.db import get_engine, init_db
    engine = get_engine()
    init_db(engine)

session = get_session(engine)

# --- Tabs ---
tab_ingestion, tab_upload, tab_db, tab_maintenance = st.tabs(
    ["Ingestion", "Upload PDF", "Base de donnees", "Maintenance"]
)

# ============================================================
# Tab 1: Ingestion
# ============================================================
with tab_ingestion:
    st.subheader("Ingestion des donnees")

    extractions_dir = config.get("ingestion", {}).get("extractions_dir", "../output/extractions")
    abs_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", extractions_dir))

    st.text(f"Repertoire source : {abs_dir}")

    if st.button("Lancer l'ingestion", key="btn_ingest"):
        if os.path.isdir(abs_dir):
            with st.spinner("Ingestion en cours..."):
                stats = ingest_directory(session, abs_dir)
            st.success(
                f"Ingestion terminee : {stats['ingested']} importes, "
                f"{stats['skipped']} deja presents, {stats['errors']} erreurs."
            )
            if stats["files"]:
                st.json(stats["files"])
        else:
            st.error(f"Repertoire introuvable : {abs_dir}")

# ============================================================
# Tab 2: Upload PDF
# ============================================================
with tab_upload:
    st.subheader("Deposer des fichiers PDF")

    upload_cfg = config.get("upload", {})
    max_size_mb = upload_cfg.get("max_file_size_mb", 50)
    upload_dir_rel = upload_cfg.get("directory", "data/uploads")
    # Resolve relative to the dashboard directory
    upload_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", upload_dir_rel)
    )

    uploaded_files = st.file_uploader(
        "Deposer vos fichiers PDF",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.read()
            file_size = len(file_bytes)
            file_size_mb = file_size / (1024 * 1024)

            st.write(f"**{uploaded_file.name}** ({file_size_mb:.1f} Mo)")

            # --- Size check ---
            if file_size_mb > max_size_mb:
                st.error(
                    f"Fichier trop volumineux ({file_size_mb:.1f} Mo). "
                    f"Limite : {max_size_mb} Mo."
                )
                continue

            # --- Duplicate check via hash ---
            content_hash = hashlib.sha256(file_bytes).hexdigest()
            existing = check_duplicate(session, content_hash)
            if existing is not None:
                st.warning(
                    f"Doublon detecte : ce fichier a deja ete uploade "
                    f"sous le nom '{existing.filename}' "
                    f"(statut : {existing.status})."
                )
                continue

            # --- Save and record ---
            with st.spinner(f"Enregistrement de {uploaded_file.name}..."):
                file_path, content_hash = save_upload(file_bytes, uploaded_file.name, upload_dir)
                record = create_upload_record(
                    session,
                    filename=uploaded_file.name,
                    content_hash=content_hash,
                    file_size=file_size,
                )
                session.commit()

            st.success(
                f"Fichier enregistre avec succes (ID: {record.id}). "
                f"Utilisez 'Lancer l'ingestion' pour traiter les extractions."
            )

    # --- Upload history ---
    st.markdown("---")
    st.subheader("Historique des uploads")

    uploads = (
        session.query(UploadLog)
        .order_by(UploadLog.uploaded_at.desc())
        .all()
    )

    if uploads:
        rows = []
        for u in uploads:
            rows.append({
                "ID": u.id,
                "Fichier": u.filename,
                "Taille (Ko)": round(u.file_size / 1024, 1) if u.file_size else None,
                "Statut": u.status,
                "Date upload": u.uploaded_at.strftime("%Y-%m-%d %H:%M") if u.uploaded_at else "",
                "Utilisateur": u.uploaded_by,
                "Erreur": u.error_message or "",
            })
        df = pd.DataFrame(rows)

        # Colour-code the status column
        def _style_status(val):
            colors = {
                "uploaded": "background-color: #fff3cd",
                "processing": "background-color: #cce5ff",
                "completed": "background-color: #d4edda",
                "failed": "background-color: #f8d7da",
            }
            return colors.get(val, "")

        st.dataframe(
            df.style.map(_style_status, subset=["Statut"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Aucun upload enregistre.")

# ============================================================
# Tab 3: Base de donnees
# ============================================================
with tab_db:
    st.subheader("Etat de la base de donnees")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Documents", session.query(func.count(Document.id)).scalar())
    with col2:
        st.metric("Lignes", session.query(func.count(LigneFacture.id)).scalar())
    with col3:
        st.metric("Fournisseurs", session.query(func.count(Fournisseur.id)).scalar())
    with col4:
        st.metric("Anomalies", session.query(func.count(Anomalie.id)).scalar())

    # Upload stats
    st.markdown("---")
    st.subheader("Statistiques uploads")
    col_u1, col_u2, col_u3, col_u4 = st.columns(4)
    with col_u1:
        st.metric("Total uploads", session.query(func.count(UploadLog.id)).scalar())
    with col_u2:
        st.metric(
            "Completes",
            session.query(func.count(UploadLog.id))
            .filter(UploadLog.status == "completed")
            .scalar(),
        )
    with col_u3:
        st.metric(
            "En attente",
            session.query(func.count(UploadLog.id))
            .filter(UploadLog.status == "uploaded")
            .scalar(),
        )
    with col_u4:
        st.metric(
            "Echoues",
            session.query(func.count(UploadLog.id))
            .filter(UploadLog.status == "failed")
            .scalar(),
        )

# ============================================================
# Tab 4: Maintenance
# ============================================================
with tab_maintenance:
    st.subheader("Maintenance")
    if st.button("Reinitialiser la base de donnees", type="secondary", key="btn_reset"):
        from dashboard.data.models import Base
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        st.success("Base de donnees reinitialisee.")
        st.rerun()

session.close()
