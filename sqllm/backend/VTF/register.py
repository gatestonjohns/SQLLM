from .pdf_llm import LLMPDFToTableVTF
from .table_llm import LLMTableToTableVTF
from .join_llm import LLMJoinVTF

ACTIVE_VTF_HANDLERS = [LLMPDFToTableVTF(), LLMTableToTableVTF(), LLMJoinVTF()]


def get_vtf_handlers():
    """Returns all of the Virtual Table Functions in ACTIVE_VTF_HANDLERS."""
    return ACTIVE_VTF_HANDLERS
