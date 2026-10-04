"""Typed tools over the domain services.

These are what an agent is allowed to call. They are framework-independent on purpose: the
Agents SDK and the MCP server are both thin adapters over this module, so the rules about what
a caller may ask for live in one place rather than being re-expressed, slightly differently,
in each binding.
"""
