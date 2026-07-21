"""Tương thích import cho biểu diễn JSON và AAD của lớp mã hóa."""

from src.integrity.serialization import canonical_json_bytes, make_aad

__all__ = ["canonical_json_bytes", "make_aad"]
