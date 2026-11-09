"""RPG_Forge — a local, file-driven art foundry for 2D games.

Jobs are JSON files in jobs/pending/. A worker (GPU or CPU) claims them, runs them, and
writes results to out/<job-id>/. Anyone who can write a JSON file can drive it — a person,
a script, or an AI assistant working through a shared folder.
"""
__version__ = "0.1.0"
