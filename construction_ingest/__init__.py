"""Zero-cloud-cost ingestion engine for Australian building practice data.

Three local layers, no third-party AI SDKs and no paid cloud APIs:

- ``db_setup``            postcode -> ABCB/NCC climate zone SQLite lookup
- ``construction_matrix`` construction phase x framing type x climate zone rules
- ``local_pdf_parser``    local PDF technical data sheets -> structured JSON via Ollama

``main`` wires them together into a single query pipeline.

Everything the pipeline emits is a *screening aid*. Climate-zone boundaries do
not follow postcode boundaries, and NCC compliance is decided by the project
energy report, condensation analysis and the building certifier - never by this
package.
"""
from __future__ import annotations

__all__ = ["db_setup", "construction_matrix", "local_pdf_parser"]
