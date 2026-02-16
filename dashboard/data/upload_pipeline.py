"""Upload pipeline for PDF file ingestion.

Handles saving uploaded PDFs, deduplication via content hash,
and optional text extraction when tools/pdf_reader.py is available.
"""

import hashlib
import json
import os

from sqlalchemy.orm import Session

from dashboard.data.models import UploadLog


def save_upload(file_bytes: bytes, filename: str, upload_dir: str) -> tuple[str, str]:
    """Save file to upload_dir, return (file_path, sha256_hash).

    Creates the upload_dir if it does not exist.
    Sanitises filename to prevent path traversal attacks.
    """
    os.makedirs(upload_dir, exist_ok=True)

    # Sanitise: take only the basename to prevent path traversal
    safe_name = os.path.basename(filename)
    if not safe_name:
        safe_name = "upload.pdf"

    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Use hash prefix to avoid filename collisions
    dest_name = f"{content_hash[:12]}_{safe_name}"
    file_path = os.path.join(upload_dir, dest_name)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    return file_path, content_hash


def check_duplicate(session: Session, content_hash: str) -> UploadLog | None:
    """Check if a file with the same hash already exists.

    Returns the existing UploadLog entry or None.
    """
    return (
        session.query(UploadLog)
        .filter(UploadLog.content_hash == content_hash)
        .first()
    )


def create_upload_record(
    session: Session,
    filename: str,
    content_hash: str,
    file_size: int,
    uploaded_by: str = "admin",
) -> UploadLog:
    """Create an UploadLog entry with status='uploaded'."""
    record = UploadLog(
        filename=filename,
        content_hash=content_hash,
        file_size=file_size,
        uploaded_by=uploaded_by,
        status="uploaded",
    )
    session.add(record)
    session.flush()
    return record


def process_upload(
    session: Session,
    upload_id: int,
    upload_dir: str,
    extractions_dir: str,
) -> UploadLog:
    """Run extraction pipeline on uploaded PDF.

    Steps:
        1. Import and call pdf_reader.extract_auto() for text extraction
        2. Save raw extraction result as JSON
        3. If structured extraction JSON available, run ingest_extraction_json()
        4. Update UploadLog status to 'completed' or 'failed'

    Note: Full LLM-based extraction requires the Extractor agent and is
    triggered separately. This function handles the text extraction step.
    """
    record = session.get(UploadLog, upload_id)
    if record is None:
        raise ValueError(f"UploadLog with id={upload_id} not found")

    record.status = "processing"
    session.flush()

    # Resolve the PDF file path
    file_path = _find_upload_file(upload_dir, record.content_hash, record.filename)
    if file_path is None:
        record.status = "failed"
        record.error_message = f"Fichier introuvable dans {upload_dir}"
        session.flush()
        return record

    os.makedirs(extractions_dir, exist_ok=True)

    # Attempt text extraction via pdf_reader (from parent project)
    try:
        import sys

        # Add parent project tools/ to path if needed
        tools_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools")
        )
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)

        from pdf_reader import extract_auto  # type: ignore[import-not-found]

        raw_result = extract_auto(file_path)

        # Save raw extraction JSON
        base_name = os.path.splitext(record.filename)[0]
        raw_json_path = os.path.join(extractions_dir, f"{base_name}_raw.json")
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_result, f, ensure_ascii=False, indent=2)

        # If the result looks like a structured extraction, attempt ingestion
        if isinstance(raw_result, dict) and "fichier" in raw_result:
            try:
                from dashboard.data.ingestion import ingest_extraction_json

                doc = ingest_extraction_json(session, raw_result)
                if doc is not None:
                    record.document_id = doc.id
            except Exception as e:
                # Ingestion failure is non-fatal; raw extraction still succeeded
                record.error_message = f"Extraction OK, ingestion echouee: {e}"

        record.status = "completed"

    except ImportError:
        # pdf_reader not available -- mark as uploaded (awaiting manual extraction)
        record.status = "uploaded"
        record.error_message = (
            "pdf_reader non disponible -- extraction manuelle requise"
        )

    except Exception as e:
        record.status = "failed"
        record.error_message = str(e)

    session.flush()
    return record


def _find_upload_file(
    upload_dir: str, content_hash: str, filename: str
) -> str | None:
    """Locate the uploaded file in upload_dir by hash prefix + filename."""
    safe_name = os.path.basename(filename) or "upload.pdf"
    expected = os.path.join(upload_dir, f"{content_hash[:12]}_{safe_name}")
    if os.path.isfile(expected):
        return expected
    return None
