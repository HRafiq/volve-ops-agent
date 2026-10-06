"""Typed tools over the domain services.

These are what an agent is allowed to call. They are framework-independent on purpose: the MCP
server is a thin adapter over this module, and an Agents SDK binding would be another, so the
rules about what a caller may ask for live in one place rather than being re-expressed, slightly
differently, in each.
"""
