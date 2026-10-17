"""Verify retained source integrity; hashes alone do not certify authenticity."""
import hashlib
from pathlib import Path
from urllib.parse import urlparse


def source_integrity(path: Path, provenance: dict) -> bool:
    if not isinstance(provenance, dict) or provenance.get('kind') not in (
            'ARCHIVED_OBSERVATIONS', 'ARCHIVED_TRADES'):
        return False
    source_file, digest = provenance.get('source_file'), provenance.get('source_sha256')
    source_url = provenance.get('source_url')
    if not isinstance(source_url, str):
        return False
    url = urlparse(source_url)
    if not isinstance(source_file, str) or not isinstance(digest, str) or url.scheme != 'https' or not url.netloc:
        return False
    root = path.parent.resolve()
    source = (root / source_file).resolve()
    if not source.is_relative_to(root / 'sources') or not source.is_file():
        return False
    return hashlib.sha256(source.read_bytes()).hexdigest() == digest
