"""Observability for VanessaAI.

Layers:
- ``metrics`` — Prometheus metrics (turns, latency, LLM tokens/errors, RAG, Telegram).
- ``tracing`` — Langfuse LLM/RAG tracing behind a NullTracer when disabled.
- ``alerting`` — periodic in-process alert evaluation with Telegram delivery.
- ``eval`` — RAG Triad evaluation (deterministic signals + LLM-as-judge sampler).
"""
