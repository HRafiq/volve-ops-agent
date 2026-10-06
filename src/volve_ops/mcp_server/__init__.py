"""MCP adapter over the domain tools.

Deliberately thin, and deliberately optional. The domain services and the tool layer work
without MCP installed; this package binds them to one protocol so an external host can call
them. Nothing here decides anything.
"""
