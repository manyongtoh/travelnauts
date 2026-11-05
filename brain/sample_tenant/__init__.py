"""Wolkenwaai Reizen: an invented Dutch family tour operator, the core's sample tenant for tests and demos.

Nothing here belongs to a client. A client's own pack lives in its own repo and registers itself under the
`brain.tenants` entry point group, exactly like this one.
"""
from pathlib import Path

from ..tenant import TenantPack, pack_from_dir


def pack() -> TenantPack:
    return pack_from_dir(Path(__file__).parent)
