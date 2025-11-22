"""Prompts module for the data agent graph."""

from graphs.prompts.intent_classification import INTENT_CLASSIFICATION_PROMPT
from graphs.prompts.search_attributes_extraction import SEARCH_ATTRIBUTES_EXTRACTION_PROMPT

__all__ = [
    "INTENT_CLASSIFICATION_PROMPT",
    "SEARCH_ATTRIBUTES_EXTRACTION_PROMPT",
]
