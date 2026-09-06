"""Worker-side task handlers: one per ``TaskKind``.

Each handler owns the heavy work that used to run inside the API process —
embedding + Qdrant indexing, the knowledge sweep, portrait regeneration and
the knowledge-vector reindex — so it can be CPU/RAM-isolated in its own
container.
"""

from services.worker.handlers.assembly import (
    WorkerAssembly,
    WorkerTaskHandler,
    build_worker_handlers,
)
from services.worker.handlers.inbox import InboxNoteHandler
from services.worker.handlers.index import IndexMessageHandler
from services.worker.handlers.knowledge import (
    MemoryExtractHandler,
    MetricsSnapshotHandler,
    PortraitHandler,
    ReindexKnowledgeHandler,
    SweepHandler,
)
from services.worker.handlers.photo import PhotoCaptionHandler

__all__ = [
    "InboxNoteHandler",
    "IndexMessageHandler",
    "MemoryExtractHandler",
    "MetricsSnapshotHandler",
    "PhotoCaptionHandler",
    "PortraitHandler",
    "ReindexKnowledgeHandler",
    "SweepHandler",
    "WorkerAssembly",
    "WorkerTaskHandler",
    "build_worker_handlers",
]
