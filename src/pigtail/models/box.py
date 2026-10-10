"""Boxes: physical containers only (NEC Art. 314)."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from pigtail.models._base import BaseModel
from pigtail.models._dot import esc
from pigtail.models.types import AwgSize, BoxAdditionKind, BoxMaterial, BoxShape, BoxType
from pigtail.nec_tables import TABLE_314_16_A


class _Volume(BaseModel):
    """A volume given one of two ways (314.16(A)): the ``shape`` and
    ``trade_size`` of a standard box, looked up in Table 314.16(A), or the
    ``volume_cu_in`` marked on it. Neither: none recorded. The depth (314.24)
    comes with the trade size; otherwise ``depth_in`` gives it.
    """

    shape: BoxShape | None = None  # Table 314.16(A), e.g. square
    trade_size: str | None = None  # Table 314.16(A) "Box Trade Size", inches, e.g. "4 x 2-1/8"
    volume_cu_in: float | None = Field(default=None, gt=0)  # as marked
    depth_in: float | None = Field(
        default=None, gt=0
    )  # internal depth, when no trade size gives it

    def _name(self) -> str:
        raise NotImplementedError

    @model_validator(mode="after")
    def _volume_given_once(self) -> Self:
        if (self.shape is None) != (self.trade_size is None):
            raise ValueError(f"{self._name()}: give shape and trade_size together")
        if self.shape is not None and self.volume_cu_in is not None:
            raise ValueError(
                f"{self._name()}: give its trade size (Table 314.16(A)) or its marked "
                "volume_cu_in, not both"
            )
        if self.shape is not None and self.depth_in is not None:
            raise ValueError(f"{self._name()}: its trade size gives its depth; drop depth_in")
        if self.shape is not None and self.trade_size not in TABLE_314_16_A[self.shape]:
            sizes = ", ".join(TABLE_314_16_A[self.shape])
            raise ValueError(
                f"{self._name()}: {self.shape} {self.trade_size!r} is not in Table 314.16(A); "
                f"its {self.shape} trade sizes are {sizes}"
            )
        return self

    @property
    def recorded_cu_in(self) -> float | None:
        """Table 314.16(A)'s minimum volume for the shape and trade size, or the
        marked volume; None when neither is recorded.
        """
        if self.shape is not None and self.trade_size is not None:
            return TABLE_314_16_A[self.shape][self.trade_size]["in3"]
        return self.volume_cu_in

    @property
    def own_depth_in(self) -> float | None:
        """The depth: the last dimension of the Table 314.16(A) trade size (a
        box's depth; an FS / FD box's is its only one), or ``depth_in``.
        """
        if self.trade_size is not None:
            return _inches(self.trade_size.split(" x ")[-1])
        return self.depth_in

    @property
    def basis(self) -> str:
        """Where the volume comes from."""
        if self.shape is not None:
            return f"Table 314.16(A), {self.trade_size} {self.shape}"
        return "marked" if self.volume_cu_in is not None else "not recorded"


def _inches(text: str) -> float:
    """A trade dimension in inches, e.g. "2-1/8" -> 2.125, "2" -> 2.0."""
    whole, _, fraction = text.partition("-")
    if "/" in whole:  # a bare fraction
        whole, fraction = "0", whole
    num, _, den = fraction.partition("/")
    return float(whole) + (float(num) / float(den) if fraction else 0.0)


class BoxAddition(_Volume):
    """314.16(A): a plaster ring, domed cover, extension ring, or raised cover
    assembled on a box. Its space counts toward the box volume when it is
    marked with its volume or made from a box whose dimensions are in Table
    314.16(A); otherwise it is recorded, but its space does not count.
    """

    kind: BoxAdditionKind

    def _name(self) -> str:
        return self.kind

    @property
    def counted_cu_in(self) -> float:
        return self.recorded_cu_in or 0.0

    @property
    def summary(self) -> str:
        if self.recorded_cu_in is None:
            return f"{self.kind} not marked, not counted"
        return f"+ {self.kind} {self.recorded_cu_in:g} in.³ ({self.basis})"


class Box(_Volume):
    """An enclosure for splices, a device, or a luminaire outlet, covered by NEC
    Article 314 (outlet, device, pull, and junction boxes).

    Its box volume (314.16(A)) is its own -- the ``shape`` and ``trade_size``
    of a standard box, looked up in Table 314.16(A) (314.16(A)(1)), or the
    ``volume_cu_in`` marked on the box (314.16(A)(2), or a standard box marked
    with its volume) -- plus the space of the ``additions`` assembled on it
    (rings, covers) that count. Without its own volume recorded, the box
    volume is not known, and 314.16 is not checked.
    """

    id: str
    type: BoxType
    material: BoxMaterial
    additions: list[BoxAddition] = []  # 314.16(A): rings and covers assembled on the box
    # conductors counted in the box but belonging to runs not yet modelled --
    # AWG -> how many; they count toward its 314.16(B) fill
    extra_conductors: dict[AwgSize, int] = {}

    def _name(self) -> str:
        return f"box {self.id!r}"

    @property
    def box_volume_cu_in(self) -> float | None:
        """314.16(A): the box's own volume plus the space of its additions that
        count; None when the box's own volume is not recorded.
        """
        own = self.recorded_cu_in
        return None if own is None else own + sum(a.counted_cu_in for a in self.additions)

    @property
    def depth_parts(self) -> list[tuple[str, float | None]]:
        """314.24(B): the box's depth, then each ring or cover's -- the internal
        depth is their sum. None where a depth is not recorded.
        """
        return [("box", self.own_depth_in), *((a.kind, a.own_depth_in) for a in self.additions)]

    @property
    def volume_basis(self) -> str:
        """Where the box volume comes from: the box, then each addition."""
        return "; ".join([self.basis, *(a.summary for a in self.additions)])

    # --- diagram --------------------------------------------------------
    def diagram_cluster(
        self, inner: list[str], *, same_rank: list[str], fill: float | None
    ) -> list[str]:
        """This box as a rounded cluster wrapping already-rendered node lines
        (its devices and its splice bar), labelled with its box volume
        (314.16(A)) and its box ``fill`` (314.16(B)). ``same_rank`` node ids are
        pinned to one rank so the splice bar sits in a row beside the device(s).
        """
        volume = (
            "box volume not recorded"
            if self.box_volume_cu_in is None
            else f"box volume {self.box_volume_cu_in:g} in.³ ({self.volume_basis})"
        )
        filled = "box fill not calculated" if fill is None else f"box fill {fill:.2f} in.³"
        out = [
            f'  subgraph "cluster_{self.id}" {{',
            f'    label="{esc(self.id)}  ·  {self.type} · {self.material} · {volume} · {filled}";',
            '    labelloc=b; style="rounded,filled"; fillcolor="#f6f6f6"; color="#bbbbbb"; fontsize=8;',
            *(f"  {line}" for line in inner),
        ]
        if len(same_rank) > 1:
            out.append("    { rank=same; " + " ".join(f'"{n}"' for n in same_rank) + " }")
        out.append("  }")
        return out
