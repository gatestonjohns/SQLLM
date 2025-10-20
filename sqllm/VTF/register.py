from .pdf_llm import LLMPDFToTableVTF
from .table_llm import LLMTableToTableVTF

ACTIVE_VTF_HANDLERS = [LLMPDFToTableVTF(), LLMTableToTableVTF()]


def get_vtf_handlers():
    """Returns all of the Virtual Table Functions in ACTIVE_VTF_HANDLERS."""
    return ACTIVE_VTF_HANDLERS
