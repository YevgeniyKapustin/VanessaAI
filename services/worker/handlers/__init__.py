"""Worker-side task handlers: one per ``TaskKind``.

Each handler owns the heavy work that used to run inside the API process —
the knowledge sweep, portrait regeneration, memory extraction, metrics and
photo captions — so it can be CPU/RAM-isolated in its own container.
"""

from services.worker.handlers.assembly import (
    WorkerAssembly,
    WorkerTaskHandler,
    build_worker_handlers,
)
from services.worker.handlers.inbox import InboxNoteHandler
from services.worker.handlers.knowledge import (
    MemoryExtractHandler,
    MetricsSnapshotHandler,
    PortraitHandler,
    SweepHandler,
)
from services.worker.handlers.photo import PhotoCaptionHandler

__all__ = [
    "InboxNoteHandler",
    "MemoryExtractHandler",
    "MetricsSnapshotHandler",
    "PhotoCaptionHandler",
    "PortraitHandler",
    "SweepHandler",
    "WorkerAssembly",
    "WorkerTaskHandler",
    "build_worker_handlers",
]
