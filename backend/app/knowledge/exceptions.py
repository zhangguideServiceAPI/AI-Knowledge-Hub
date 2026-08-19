class KnowledgeBaseNotFoundError(Exception):
    """KnowledgeBase does not exist or does not belong to the current user."""


class KnowledgeDocumentWriteError(Exception):
    """KnowledgeDocument metadata could not be committed to the database."""


class KnowledgeDocumentNotFoundError(Exception):
    """KnowledgeDocument does not exist or is outside the current user's scope."""


class KnowledgeVersionWriteError(Exception):
    """DocumentVersion or its chunks could not be committed."""
