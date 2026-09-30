"""Closed vocabularies used across the models -- every Literal alias, named, in
one place. Model files never spell out a ``Literal`` inline.
"""

from __future__ import annotations

from typing import Literal

# --- supply / circuit -------------------------------------------------------
# A "leg" is one ungrounded (hot) conductor of the 120/240 V single-phase
# 3-wire service. The utility transformer's centre-tapped secondary gives two
# legs 180 deg apart: L1-to-neutral and L2-to-neutral are each 120 V, L1-to-L2
# is 240 V. Every 1-pole breaker clips onto one leg; a 2-pole breaker spans
# both. (NEC calls them "ungrounded conductors"; "leg" is the trade term.)
type Line = Literal["L1", "L2"]
type PanelboardBus = Line | Literal["NEUTRAL", "EGC"]  # a panelboard busbar
type BreakerPoles = Literal[1, 2]  # 1-pole 120 V, 2-pole 240 V (split-phase has no 3-pole)

# --- conductors -----------------------------------------------------------
# NEC Art. 100: "ungrounded" = a hot; "neutral" = the grounded conductor that
# carries unbalanced current; "traveler" = the pair between 3-/4-way switches;
# "egc" = equipment grounding conductor (the fault-current path, 250.118).
type ConductorRole = Literal["ungrounded", "traveler", "neutral", "egc"]
type ConductorColor = Literal["black", "red", "blue", "yellow", "white", "gray", "green", "bare"]
type ConductorMaterial = Literal["Cu", "Al"]
# "rubber" is the historic insulation of knob-and-tube conductors (Code type R);
# "bare" covers a wire EGC and a metal raceway acting as one.
type Insulation = Literal[
    "TW", "THWN", "THHN", "THWN-2", "XHHW-2", "rubber", "bare"
]  # NEC Table 310.4(A)
# 310.3(C): conductors 8 AWG and larger in a raceway are stranded
type Stranding = Literal["solid", "stranded"]
# 110.14(C): a terminal's temperature rating -- 60 C unless the equipment is marked 75 C
type TerminalTemp = Literal[60, 75]
type ConductorCount = Literal[2, 3]  # insulated circuit conductors in a run; EGC additional
type AwgSize = Literal[14, 12, 10, 8, 6, 4, 3, 2]  # AWG, NEC Table 310.16 (kcmil comes later)

# --- wiring methods ---------------------------------------------------
# How circuit conductors get from box to box:
#   NM-B          jacketed assembly, its own wire EGC             (NEC Art. 334)
#   knob_and_tube loose single conductors on porcelain supports,
#                 two wires only -- NO equipment grounding conductor (NEC Art. 394)
#   EMT           steel raceway; wires pulled in, and the tubing
#                 itself is the EGC (NEC Art. 358, 250.118(A)(4))
type WiringMethod = Literal["NM-B", "knob_and_tube", "EMT"]

# EMT trade (nominal) size in inches -- the tubing you buy, distinct from the
# AWG of the conductors pulled through it (NEC Art. 358, Chapter 9 tables).
type EmtTradeSize = Literal["1/2", "3/4", "1", "1-1/4", "1-1/2", "2"]

# --- boxes -------------------------------------------------------------
type BoxType = Literal["device", "outlet", "junction", "pull"]  # NEC Art. 314
type BoxMaterial = Literal["nonmetallic", "metal"]  # NEC 314.3
# 314.16(A): the sections assembled on a box whose space counts in its volume
type BoxAdditionKind = Literal["extension ring", "plaster ring", "domed cover", "raised cover"]
# the box shapes of Table 314.16(A) Metal Boxes, as the table names them
type BoxShape = Literal[
    "round/octagonal",
    "square",
    "device",
    "masonry box/gang",
    "FS single cover/gang",
    "FD single cover/gang",
    "FS multiple cover/gang",
    "FD multiple cover/gang",
]

# --- devices ---------------------------------------------------------
# The discriminator tag (`type: Literal["snap_switch"]` etc.) stays inline on
# each model -- it is not a reusable vocabulary, just a tag.
type SwitchFunction = Literal["single_pole", "three_way", "four_way"]  # NEC 404.2

# NEMA straight-blade / locking receptacle configurations seen in a house
# (ANSI/NEMA WD 6). 1-15R = the old ungrounded 2-prong; 6-xx = straight 240 V
# (no neutral); 14-xx = 120/240 V (with neutral); L = twist-lock.
type NemaConfig = Literal[
    "1-15R",
    "5-15R",
    "5-20R",
    "6-15R",
    "6-20R",
    "6-30R",
    "6-50R",
    "10-30R",
    "10-50R",
    "14-30R",
    "14-50R",
    "L5-20R",
    "L6-20R",
    "L14-30R",
]

# --- terminals -----------------------------------------------------
# A device/breaker connection point. LINE/LOAD are the 1-pole (120 V) pair;
# LINE1/LINE2/LOAD1/LOAD2 are the 2-pole (240 V) set.
type Terminal = Literal["LINE", "LOAD", "NEUTRAL", "EGC", "LINE1", "LINE2", "LOAD1", "LOAD2"]
