"""Background worker service.

The agent core publishes fire-and-forget ``TaskMessage``s to the broker; this
worker consumes them (``WorkerApp``) and runs the heavy handlers (sweep,
portraits, memory, metrics, photo captions) in an isolated process so a
CPU/RAM spike never stalls the reply path.
"""
