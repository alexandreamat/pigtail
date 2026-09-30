"""NEC 2023 tables and fixed values, as data -- the single source for every
number the checks use. Each constant is named after the table or section it
transcribes; lookups go through these mappings, never through literals in the
checks. Copper only where the NEC tabulates copper and aluminum separately.

Values are transcribed from NFPA 70, National Electrical Code (2023).
"""

from __future__ import annotations

# --- Article 110 -------------------------------------------------------------

# 110.14(C)(1): terminations are assumed rated 60 C on circuits of 100 A or less
# (or 14-1 AWG), 75 C above -- unless the equipment is marked otherwise.
SECTION_110_14_C_1: dict[str, dict[str, int]] = {
    "(a)": {"max_amperes": 100, "temp_c": 60},
    "(b)": {"temp_c": 75},
}

# --- Article 210 -------------------------------------------------------------

# 210.19(A)(1) / 210.20(A): conductors and overcurrent devices are sized at
# 125 % of the continuous load plus 100 % of the noncontinuous load.
SECTION_210_19_A_1_CONTINUOUS = 1.25

# 210.19(A) Informational Note No. 4: voltage drop of 3 % on the branch circuit
# (5 % feeder + branch) gives reasonable efficiency -- advice, not a requirement.
SECTION_210_19_A_IN_4: dict[str, float] = {
    "branch_circuit": 0.03,
    "feeder_and_branch_circuit": 0.05,
}

# Table 210.21(B)(3): receptacle ratings permitted on a circuit of a given rating.
TABLE_210_21_B_3: dict[int, tuple[int, ...]] = {
    15: (15,),
    20: (15, 20),
    30: (30,),
    40: (40, 50),
    50: (50,),
}

# --- Article 220 -------------------------------------------------------------

# 220.5(A): nominal voltages for calculations -- a 1-pole (120 V) or 2-pole
# (120/240 V single-phase, line to line) circuit.
SECTION_220_5_A: dict[int, int] = {1: 120, 2: 240}

# --- Article 240 -------------------------------------------------------------

# 240.4(B): the next standard rating above a conductor's ampacity, up to 800 A.
SECTION_240_4_B_MAX_AMPERES = 800

# 240.4(D): small-conductor overcurrent limits, copper, after any correction
# and adjustment.
SECTION_240_4_D: dict[str, dict[int, int]] = {"Cu": {14: 15, 12: 20, 10: 30}}

# 240.6(A): standard ampere ratings of fuses and inverse-time circuit breakers.
TABLE_240_6_A: tuple[int, ...] = (
    15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 125, 150, 175, 200, 225, 250, 300,
    350, 400, 450, 500, 600, 700, 800, 1000, 1200, 1600, 2000, 2500, 3000, 4000, 5000, 6000,
)  # fmt: skip

# --- Article 250 -------------------------------------------------------------

# Table 250.122: minimum copper equipment grounding conductor, by the rating of
# the overcurrent device ahead of it -- (up to amperes, AWG).
TABLE_250_122: dict[str, tuple[tuple[int, int], ...]] = {
    "Cu": ((15, 14), (20, 12), (60, 10), (100, 8), (200, 6), (300, 4), (400, 3), (500, 2)),
}

# --- Article 310 -------------------------------------------------------------

# Table 310.15(B)(1)(1): ambient temperature correction, based on 30 C --
# (lowest C, highest C) -> {insulation temperature rating: factor}. None: the
# insulation may not be used at that ambient.
TABLE_310_15_B_1_1: dict[tuple[int, int], dict[int, float | None]] = {
    (-99, 10): {60: 1.29, 75: 1.20, 90: 1.15},
    (11, 15): {60: 1.22, 75: 1.15, 90: 1.12},
    (16, 20): {60: 1.15, 75: 1.11, 90: 1.08},
    (21, 25): {60: 1.08, 75: 1.05, 90: 1.04},
    (26, 30): {60: 1.00, 75: 1.00, 90: 1.00},
    (31, 35): {60: 0.91, 75: 0.94, 90: 0.96},
    (36, 40): {60: 0.82, 75: 0.88, 90: 0.91},
    (41, 45): {60: 0.71, 75: 0.82, 90: 0.87},
    (46, 50): {60: 0.58, 75: 0.75, 90: 0.82},
    (51, 55): {60: 0.41, 75: 0.67, 90: 0.76},
    (56, 60): {60: None, 75: 0.58, 90: 0.71},
    (61, 65): {60: None, 75: 0.47, 90: 0.65},
    (66, 70): {60: None, 75: 0.33, 90: 0.58},
    (71, 75): {60: None, 75: None, 90: 0.50},
    (76, 80): {60: None, 75: None, 90: 0.41},
    (81, 85): {60: None, 75: None, 90: 0.29},
}

# Table 310.15(C)(1): adjustment for more than three current-carrying
# conductors in a raceway -- (fewest, most) -> factor.
TABLE_310_15_C_1: dict[tuple[int, int], float] = {
    (1, 3): 1.00,
    (4, 6): 0.80,
    (7, 9): 0.70,
    (10, 20): 0.50,
    (21, 30): 0.45,
    (31, 40): 0.40,
    (41, 10_000): 0.35,
}

# Table 310.16: ampacity of insulated conductors, not more than three
# current-carrying in a raceway, 30 C ambient -- material -> insulation
# temperature rating -> AWG -> amperes.
TABLE_310_16: dict[str, dict[int, dict[int, int]]] = {
    "Cu": {
        60: {14: 15, 12: 20, 10: 30, 8: 40, 6: 55, 4: 70, 3: 85, 2: 95},
        75: {14: 20, 12: 25, 10: 35, 8: 50, 6: 65, 4: 85, 3: 100, 2: 115},
        90: {14: 25, 12: 30, 10: 40, 8: 55, 6: 75, 4: 95, 3: 115, 2: 130},
    },
}

# Table 310.4(1): temperature rating of the insulation types used here.
TABLE_310_4_1: dict[str, int] = {
    "TW": 60,
    "THWN": 75,
    "THHN": 90,
    "THWN-2": 90,
    "XHHW-2": 90,
    "rubber": 60,  # knob-and-tube era rubber-covered wire
}

# 310.3(C): conductors this size and larger (8 AWG) in a raceway are stranded.
SECTION_310_3_C_STRANDED_FROM_AWG = 8

# --- Article 314 -------------------------------------------------------------

# Table 314.16(A) Metal Boxes: the minimum volume of each standard box -- box
# shape -> box trade size -> minimum volume, cm3 and in3. Trade sizes are in
# inches as the table writes them, fractions in ASCII: "4 x 2-1/8" is the
# table's (4 x 2 1/8); device boxes are width x height x depth; FS and FD boxes
# are listed by their minimum depth. The table's "Maximum Number of
# Conductors" columns are not transcribed: the box fill is calculated, 314.16(B).
TABLE_314_16_A: dict[str, dict[str, dict[str, float]]] = {
    "round/octagonal": {
        "4 x 1-1/4": {"cm3": 205, "in3": 12.5},
        "4 x 1-1/2": {"cm3": 254, "in3": 15.5},
        "4 x 2-1/8": {"cm3": 353, "in3": 21.5},
    },
    "square": {
        "4 x 1-1/4": {"cm3": 295, "in3": 18.0},
        "4 x 1-1/2": {"cm3": 344, "in3": 21.0},
        "4 x 2-1/8": {"cm3": 497, "in3": 30.3},
        "4-11/16 x 1-1/4": {"cm3": 418, "in3": 25.5},
        "4-11/16 x 1-1/2": {"cm3": 484, "in3": 29.5},
        "4-11/16 x 2-1/8": {"cm3": 689, "in3": 42.0},
    },
    "device": {
        "3 x 2 x 1-1/2": {"cm3": 123, "in3": 7.5},
        "3 x 2 x 2": {"cm3": 164, "in3": 10.0},
        "3 x 2 x 2-1/4": {"cm3": 172, "in3": 10.5},
        "3 x 2 x 2-1/2": {"cm3": 205, "in3": 12.5},
        "3 x 2 x 2-3/4": {"cm3": 230, "in3": 14.0},
        "3 x 2 x 3-1/2": {"cm3": 295, "in3": 18.0},
        "4 x 2-1/8 x 1-1/2": {"cm3": 169, "in3": 10.3},
        "4 x 2-1/8 x 1-7/8": {"cm3": 213, "in3": 13.0},
        "4 x 2-1/8 x 2-1/8": {"cm3": 238, "in3": 14.5},
    },
    "masonry box/gang": {
        "3-3/4 x 2 x 2-1/2": {"cm3": 230, "in3": 14.0},
        "3-3/4 x 2 x 3-1/2": {"cm3": 344, "in3": 21.0},
    },
    "FS single cover/gang": {"1-3/4": {"cm3": 221, "in3": 13.5}},
    "FD single cover/gang": {"2-3/8": {"cm3": 295, "in3": 18.0}},
    "FS multiple cover/gang": {"1-3/4": {"cm3": 295, "in3": 18.0}},
    "FD multiple cover/gang": {"2-3/8": {"cm3": 395, "in3": 24.0}},
}

# 314.16(B)(4): each yoke or strap carrying a device (switch, receptacle) counts
# as this many conductors of the largest size connected to it.
SECTION_314_16_B_4_PER_YOKE = 2

# Table 314.16(B): free space within a box for each conductor, by AWG, cu in.
TABLE_314_16_B: dict[int, float] = {
    18: 1.50,
    16: 1.75,
    14: 2.00,
    12: 2.25,
    10: 2.50,
    8: 3.00,
    6: 5.00,
}

# --- Article 334 -------------------------------------------------------------

# 334.80: NM cable ampacity is that of 60 C conductors, whatever the insulation.
SECTION_334_80_TEMP_C = 60

# --- Article 358 -------------------------------------------------------------

# 358.26: bends between pull points total no more than 360 degrees.
SECTION_358_26_MAX_BENDS_DEG = 360

# --- Article 625 -------------------------------------------------------------

# 625.41: EVSE overcurrent protection at not less than 125 % of its maximum load.
SECTION_625_41 = 1.25

# --- Chapter 9 ---------------------------------------------------------------

# Chapter 9 Table 1: the percentage of a conduit's cross-section conductors may fill.
CHAPTER_9_TABLE_1: dict[str, float] = {"1": 0.53, "2": 0.31, "over 2": 0.40}

# Chapter 9 Table 4: conduit dimensions -- type -> trade size -> dimensions.
CHAPTER_9_TABLE_4: dict[str, dict[str, dict[str, float]]] = {
    "EMT": {
        "1/2": {"internal_diameter_in": 0.622, "total_area_sq_in": 0.304},
        "3/4": {"internal_diameter_in": 0.824, "total_area_sq_in": 0.533},
        "1": {"internal_diameter_in": 1.049, "total_area_sq_in": 0.864},
        "1-1/4": {"internal_diameter_in": 1.380, "total_area_sq_in": 1.496},
        "1-1/2": {"internal_diameter_in": 1.610, "total_area_sq_in": 2.036},
        "2": {"internal_diameter_in": 2.067, "total_area_sq_in": 3.356},
    },
}

# Chapter 9 Table 5: insulated conductor dimensions -- type -> AWG -> dimensions.
_THHN: dict[int, dict[str, float]] = {
    14: {"diameter_in": 0.111, "area_sq_in": 0.0097},
    12: {"diameter_in": 0.130, "area_sq_in": 0.0133},
    10: {"diameter_in": 0.164, "area_sq_in": 0.0211},
    8: {"diameter_in": 0.216, "area_sq_in": 0.0366},
    6: {"diameter_in": 0.254, "area_sq_in": 0.0507},
    4: {"diameter_in": 0.324, "area_sq_in": 0.0824},
    3: {"diameter_in": 0.352, "area_sq_in": 0.0973},
    2: {"diameter_in": 0.384, "area_sq_in": 0.1158},
}
CHAPTER_9_TABLE_5: dict[str, dict[int, dict[str, float]]] = {
    "THHN": _THHN,
    "THWN": _THHN,
    "THWN-2": _THHN,
    "TW": {
        14: {"diameter_in": 0.133, "area_sq_in": 0.0139},
        12: {"diameter_in": 0.152, "area_sq_in": 0.0181},
        10: {"diameter_in": 0.176, "area_sq_in": 0.0243},
        8: {"diameter_in": 0.236, "area_sq_in": 0.0437},
    },
    "XHHW-2": {
        14: {"diameter_in": 0.133, "area_sq_in": 0.0139},
        12: {"diameter_in": 0.152, "area_sq_in": 0.0181},
        10: {"diameter_in": 0.176, "area_sq_in": 0.0243},
        8: {"diameter_in": 0.236, "area_sq_in": 0.0437},
        6: {"diameter_in": 0.274, "area_sq_in": 0.0590},
        4: {"diameter_in": 0.322, "area_sq_in": 0.0814},
        3: {"diameter_in": 0.350, "area_sq_in": 0.0962},
        2: {"diameter_in": 0.382, "area_sq_in": 0.1146},
    },
}

# Chapter 9 Table 8: conductor properties -- AWG -> {"area_cmil",
# stranding -> DC resistance at 75 C, ohm per 1000 ft, uncoated copper}.
CHAPTER_9_TABLE_8: dict[int, dict[str, float]] = {
    14: {"area_cmil": 4110, "solid": 3.07, "stranded": 3.14},
    12: {"area_cmil": 6530, "solid": 1.93, "stranded": 1.98},
    10: {"area_cmil": 10380, "solid": 1.21, "stranded": 1.24},
    8: {"area_cmil": 16510, "solid": 0.764, "stranded": 0.778},
    6: {"area_cmil": 26240, "stranded": 0.491},
    4: {"area_cmil": 41740, "stranded": 0.308},
    3: {"area_cmil": 52620, "stranded": 0.245},
    2: {"area_cmil": 66360, "stranded": 0.194},
}
