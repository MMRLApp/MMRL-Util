# NOTE: this patches the standard zipfile module
from . import _zipfile

from zipfile import *
from zipfile import (
    ZIP_XZ,
    XZ_VERSION,
)

__all__ = [
    "ZIP_XZ",
    "XZ_VERSION",
    "_zipfile"
]