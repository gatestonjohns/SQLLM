from .pdf_llm import LLMPDFToTableVTF

ACTIVE_VTF_HANDLERS: list[LLMPDFToTableVTF] = [LLMPDFToTableVTF()]


def get_vtf_handlers() -> list[LLMPDFToTableVTF]:
    return ACTIVE_VTF_HANDLERS
