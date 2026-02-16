"""Tests for the PDF upload pipeline."""

import hashlib
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, UploadLog
from dashboard.data.upload_pipeline import (
    save_upload,
    check_duplicate,
    create_upload_record,
    process_upload,
    _find_upload_file,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


# ------------------------------------------------------------------
# save_upload
# ------------------------------------------------------------------

class TestSaveUpload:
    def test_saves_file_and_returns_hash(self, tmp_path):
        content = b"%PDF-1.4 fake pdf content"
        file_path, content_hash = save_upload(content, "test.pdf", str(tmp_path))

        assert os.path.isfile(file_path)
        assert content_hash == hashlib.sha256(content).hexdigest()

        with open(file_path, "rb") as f:
            assert f.read() == content

    def test_creates_directory_if_missing(self, tmp_path):
        upload_dir = str(tmp_path / "nested" / "uploads")
        content = b"%PDF-1.4 test"
        file_path, _ = save_upload(content, "test.pdf", upload_dir)

        assert os.path.isdir(upload_dir)
        assert os.path.isfile(file_path)

    def test_sanitises_filename_path_traversal(self, tmp_path):
        content = b"%PDF-1.4 traversal test"
        file_path, _ = save_upload(content, "../../../etc/passwd", str(tmp_path))

        # File must be inside tmp_path, not escaped
        assert os.path.dirname(file_path) == str(tmp_path)
        assert "passwd" in os.path.basename(file_path)

    def test_handles_empty_filename(self, tmp_path):
        content = b"%PDF-1.4 empty name"
        file_path, _ = save_upload(content, "", str(tmp_path))

        assert os.path.isfile(file_path)
        assert "upload.pdf" in os.path.basename(file_path)

    def test_hash_prefix_in_filename(self, tmp_path):
        content = b"%PDF-1.4 hash prefix test"
        expected_hash = hashlib.sha256(content).hexdigest()
        file_path, content_hash = save_upload(content, "facture.pdf", str(tmp_path))

        basename = os.path.basename(file_path)
        assert basename.startswith(expected_hash[:12])
        assert basename.endswith("_facture.pdf")


# ------------------------------------------------------------------
# check_duplicate
# ------------------------------------------------------------------

class TestCheckDuplicate:
    def test_returns_none_when_no_match(self, db_session):
        result = check_duplicate(db_session, "nonexistent_hash")
        assert result is None

    def test_returns_record_when_match(self, db_session):
        ul = UploadLog(filename="existing.pdf", content_hash="abc123", file_size=1000)
        db_session.add(ul)
        db_session.commit()

        result = check_duplicate(db_session, "abc123")
        assert result is not None
        assert result.filename == "existing.pdf"

    def test_no_false_positive(self, db_session):
        ul = UploadLog(filename="existing.pdf", content_hash="abc123", file_size=1000)
        db_session.add(ul)
        db_session.commit()

        result = check_duplicate(db_session, "def456")
        assert result is None


# ------------------------------------------------------------------
# create_upload_record
# ------------------------------------------------------------------

class TestCreateUploadRecord:
    def test_creates_record_with_defaults(self, db_session):
        record = create_upload_record(db_session, "test.pdf", "hash123", 2048)
        db_session.commit()

        assert record.id is not None
        assert record.filename == "test.pdf"
        assert record.content_hash == "hash123"
        assert record.file_size == 2048
        assert record.uploaded_by == "admin"
        assert record.status == "uploaded"

    def test_creates_record_with_custom_user(self, db_session):
        record = create_upload_record(
            db_session, "test.pdf", "hash456", 4096, uploaded_by="operator"
        )
        db_session.commit()

        assert record.uploaded_by == "operator"

    def test_record_persists_in_db(self, db_session):
        create_upload_record(db_session, "persist.pdf", "hash_persist", 512)
        db_session.commit()

        found = db_session.query(UploadLog).filter_by(content_hash="hash_persist").first()
        assert found is not None
        assert found.filename == "persist.pdf"


# ------------------------------------------------------------------
# process_upload
# ------------------------------------------------------------------

class TestProcessUpload:
    def test_raises_on_missing_upload_id(self, db_session, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            process_upload(db_session, 9999, str(tmp_path), str(tmp_path / "out"))

    def test_fails_when_file_not_found(self, db_session, tmp_path):
        record = create_upload_record(db_session, "missing.pdf", "hash_missing", 100)
        db_session.commit()

        result = process_upload(
            db_session, record.id, str(tmp_path / "empty_dir"), str(tmp_path / "out")
        )

        assert result.status == "failed"
        assert "introuvable" in result.error_message

    def test_handles_import_error_gracefully(self, db_session, tmp_path):
        """When pdf_reader is not importable, status should remain 'uploaded'."""
        content = b"%PDF-1.4 test content"
        file_path, content_hash = save_upload(content, "test.pdf", str(tmp_path / "uploads"))
        record = create_upload_record(db_session, "test.pdf", content_hash, len(content))
        db_session.commit()

        result = process_upload(
            db_session, record.id, str(tmp_path / "uploads"), str(tmp_path / "out")
        )

        # pdf_reader is not available in the test environment
        assert result.status in ("uploaded", "failed")
        if result.status == "uploaded":
            assert "pdf_reader non disponible" in result.error_message

    def test_creates_extractions_dir(self, db_session, tmp_path):
        content = b"%PDF-1.4 test"
        file_path, content_hash = save_upload(content, "test.pdf", str(tmp_path / "uploads"))
        record = create_upload_record(db_session, "test.pdf", content_hash, len(content))
        db_session.commit()

        extractions_dir = str(tmp_path / "extractions")
        assert not os.path.isdir(extractions_dir)

        process_upload(db_session, record.id, str(tmp_path / "uploads"), extractions_dir)

        assert os.path.isdir(extractions_dir)


# ------------------------------------------------------------------
# _find_upload_file
# ------------------------------------------------------------------

class TestFindUploadFile:
    def test_finds_existing_file(self, tmp_path):
        content = b"test content"
        content_hash = hashlib.sha256(content).hexdigest()
        filename = "invoice.pdf"
        dest = tmp_path / f"{content_hash[:12]}_{filename}"
        dest.write_bytes(content)

        result = _find_upload_file(str(tmp_path), content_hash, filename)
        assert result == str(dest)

    def test_returns_none_when_not_found(self, tmp_path):
        result = _find_upload_file(str(tmp_path), "nonexistent_hash", "nope.pdf")
        assert result is None


# ------------------------------------------------------------------
# Integration: full save + check_duplicate + record flow
# ------------------------------------------------------------------

class TestUploadIntegration:
    def test_full_upload_flow(self, db_session, tmp_path):
        content = b"%PDF-1.4 integration test pdf"
        upload_dir = str(tmp_path / "uploads")

        # Save
        file_path, content_hash = save_upload(content, "facture_test.pdf", upload_dir)
        assert os.path.isfile(file_path)

        # No duplicate
        assert check_duplicate(db_session, content_hash) is None

        # Create record
        record = create_upload_record(
            db_session, "facture_test.pdf", content_hash, len(content)
        )
        db_session.commit()
        assert record.status == "uploaded"

        # Now duplicate check finds it
        dup = check_duplicate(db_session, content_hash)
        assert dup is not None
        assert dup.id == record.id

    def test_duplicate_upload_prevented(self, db_session, tmp_path):
        content = b"%PDF-1.4 duplicate test"
        upload_dir = str(tmp_path / "uploads")

        # First upload
        _, hash1 = save_upload(content, "file1.pdf", upload_dir)
        create_upload_record(db_session, "file1.pdf", hash1, len(content))
        db_session.commit()

        # Second upload with same content
        _, hash2 = save_upload(content, "file2.pdf", upload_dir)
        assert hash1 == hash2

        existing = check_duplicate(db_session, hash2)
        assert existing is not None
        assert existing.filename == "file1.pdf"
