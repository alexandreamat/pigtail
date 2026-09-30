"""Shared base model, the SKiDL ad-hoc part factory, and the build-time error."""

from __future__ import annotations

from collections.abc import Callable

import pydantic
from skidl import NETLIST, SKIDL, Net, Part, Pin

from pigtail.models.types import Terminal


class BuildError(ValueError):
    """A house that cannot be assembled, or build-time state read before build()."""


def join(*items: Net | Pin) -> None:
    """Merge SKiDL nets/pins into one electrical node (``a.connect(b, c, ...)``)."""
    head, *rest = items
    head.connect(*rest)


def require[T](read: Callable[[], T], what: str) -> T:
    """Return ``read()``, or raise ``BuildError`` if it is unset (not built yet).

    Build-time state is held in defaultless PrivateAttrs, so reading one before
    ``build()`` raises ``AttributeError`` -- caught and re-raised here.
    """
    try:
        return read()
    except AttributeError:
        raise BuildError(
            f"{what}: not built -- load via House.from_yaml() or call house.build()"
        ) from None


class BaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    @staticmethod
    def _make_part(name: str, ref: str, terminals: tuple[Terminal, ...], **kwargs: object) -> Part:
        """A library-free SKiDL part: PASSIVE pins named after ``terminals``,
        ``ref`` used verbatim, extra ``kwargs`` set as attributes.
        """
        part = Part(
            name=name,
            ref_prefix="".join(c for c in ref if c.isalpha()) or "U",
            ref=ref,
            tool=SKIDL,
            dest=NETLIST,
            tag=ref,
            footprint="pigtail:device",
            pins=[Pin(num=i + 1, name=t, func=Pin.types.PASSIVE) for i, t in enumerate(terminals)],
        )
        for key, value in kwargs.items():
            setattr(part, key, value)
        return part
