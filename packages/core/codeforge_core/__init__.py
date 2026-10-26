"""Shared core for the CodeForge API and execution workers.

Everything that both processes must agree on lives here: the relational
model, the submission state machine, queue/event wire formats, language
adapters and configuration. Keeping it in one package means the API and the
worker can never disagree about what a legal state transition is.
"""
