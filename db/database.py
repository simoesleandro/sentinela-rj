"""Compatibilidade: use db.narrativa.GerenciadorNarrativa."""
from __future__ import annotations

from db.narrativa import GerenciadorBanco, GerenciadorNarrativa

__all__ = ["GerenciadorBanco", "GerenciadorNarrativa"]
