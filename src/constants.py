"""
constants.py
--------------------
Shared constants for the P&ID symbol library:
  - schema version
  - classification maps (autocad folder, downloaded folder, generated prefix, keyword heuristics)
  - compiled regex patterns
  - SVG category sets
  - SVG minification patterns
"""

import re

SCHEMA_VERSION = "1.0.0"

# Classification maps

# autocad-parser subfolder → (standard, category)
AUTOCAD_FOLDER_MAP: dict[str, tuple[str, str]] = {
    "isa_actuator_svg":      ("ISA",        "actuator"),
    "isa_equipment1_svg":    ("ISA",        "equipment"),
    "isa_equipment2_svg":    ("ISA",        "equipment"),
    "isa_flow_svg":          ("ISA",        "flow"),
    "isa_relief_valves_svg": ("ISA",        "relief_valve"),
    "isa_valves_svg":        ("ISA",        "valve"),
    "iso_agitators_svg":     ("ISO 10628-2","agitator"),
    "iso_equipment_svg":     ("ISO 10628-2","equipment"),
    "iso_instruments_svg":   ("ISO 10628-2","instrument"),
    "iso_nozzles_svg":       ("ISO 10628-2","nozzle"),
}

# pid-symbols-generator/downloaded subfolder → category
DOWNLOADED_FOLDER_MAP: dict[str, str] = {
    "agitators":                                    "agitator",
    "apparaturs_elements":                          "apparatus_element",
    "centrifuges":                                  "centrifuge",
    "check_valves":                                 "check_valve",
    "columns":                                      "column",
    "compressors":                                  "compressor",
    "cooling_towers":                               "cooling_tower",
    "crushing_machines":                            "crushing_machine",
    "driers":                                       "drier",
    "engines":                                      "engine",
    "fans":                                         "fan",
    "filters":                                      "filter",
    "fittings":                                     "fitting",
    "heat_exchangers":                              "heat_exchanger",
    "internals":                                    "internal",
    "lifting,_conveying_and_transport_equipment":   "lifting_equipment",
    "liquid_pumps":                                 "pump",
    "mixers_and_kneaders":                          "mixer",
    "pipes":                                        "pipe",
    "screening_devices,_sieves,_and_rakes":         "screening_device",
    "separators":                                   "separator",
    "shaping_machines":                             "shaping_machine",
    "steam_generators,_furnaces,_recooling_device": "steam_generator",
    "tanks_and_containers":                         "tank",
    "valves":                                       "valve",
    "ventilation":                                  "ventilation",
}

# pid-symbols-generator/generated filename prefix → (standard, category)
GENERATED_PREFIX_MAP: dict[str, tuple[str, str]] = {
    "valve_":     ("ISA", "valve"),
    "cv_":        ("ISA", "control_valve"),
    "actuator_":  ("ISA", "actuator"),
    "equip_":     ("ISA", "equipment"),
    "line_":      ("ISA", "line_type"),
    "logic_":     ("ISA", "logic"),
    "piping_":    ("ISA", "piping"),
    "safety_":    ("ISA", "safety"),
    "regulator_": ("ISA", "regulator"),
    "acc_":       ("ISA", "accessory"),
    "conn_":      ("ISA", "connection"),
    "ann_":       ("ISA", "annotation"),
    "primary_":   ("ISA", "primary_element"),
    "bubble_":    ("ISA", "instrument_bubble"),
    "fail_":      ("ISA", "fail_position"),
}

# Generic keyword heuristics applied to stem (lowercase) → category
KEYWORD_HEURISTICS: list[tuple[str, str]] = [
    ("valve",         "valve"),
    ("actuator",      "actuator"),
    ("pump",          "pump"),
    ("compressor",    "compressor"),
    ("agitator",      "agitator"),
    ("stirrer",       "agitator"),
    ("heat_exchanger","heat_exchanger"),
    ("exchanger",     "heat_exchanger"),
    ("filter",        "filter"),
    ("separator",     "separator"),
    ("centrifuge",    "centrifuge"),
    ("column",        "column"),
    ("tank",          "tank"),
    ("vessel",        "vessel"),
    ("reactor",       "reactor"),
    ("furnace",       "furnace"),
    ("boiler",        "steam_generator"),
    ("conveyor",      "lifting_equipment"),
    ("crusher",       "crushing_machine"),
    ("dryer",         "drier"),
    ("drier",         "drier"),
    ("fan",           "fan"),
    ("blower",        "fan"),
    ("instrument",    "instrument"),
    ("sensor",        "instrument"),
    ("nozzle",        "nozzle"),
    ("relief",        "relief_valve"),
    ("safety",        "safety"),
    ("solenoid",      "actuator"),
    ("diaphragm",     "actuator"),
    ("piston",        "actuator"),
    ("positioner",    "accessory"),
    ("handwheel",     "actuator"),
    ("bubble",        "instrument_bubble"),
    ("instrument",    "instrument"),
    ("logic",         "logic"),
    ("interlock",     "logic"),
    ("orifice",       "primary_element"),
    ("thermowell",    "primary_element"),
    ("venturi",       "primary_element"),
    ("pipe",          "piping"),
    ("fitting",       "fitting"),
    ("flange",        "fitting"),
    ("mixer",         "mixer"),
    ("kneader",       "mixer"),
    ("gear",          "drive"),
    ("motor",         "drive"),
    ("turbine",       "drive"),
    ("engine",        "drive"),
    # Additional heuristics for downloaded/ root files
    ("autoclave",     "reactor"),
    ("bag",           "tank"),
    ("funnel",        "fitting"),
    ("gas bottle",    "tank"),
    ("gas cylinder",  "tank"),
    ("knock-out",     "separator"),
    ("knockout",      "separator"),
    ("knock_out",     "separator"),
    ("liftequip",     "lifting_equipment"),
    ("lift equip",    "lifting_equipment"),
    ("sieve",         "screening_device"),
    ("steam trap",    "fitting"),
    ("steam_trap",    "fitting"),
    ("dust trap",     "filter"),
    ("dust_trap",     "filter"),
    ("elutriator",    "separator"),
    ("viewing glass", "instrument"),
    ("viewing_glass", "instrument"),
    ("computer function", "instrument_bubble"),
    ("control function",  "instrument_bubble"),
    ("discrete instrument", "instrument_bubble"),
    ("scrubber",      "separator"),
    ("cyclone",       "separator"),
    ("strainer",      "filter"),
    ("screen",        "screening_device"),
    ("hopper",        "tank"),
    ("bin",           "tank"),
    ("silo",          "tank"),
    ("evaporator",    "heat_exchanger"),
    ("condenser",     "heat_exchanger"),
    ("reboiler",      "heat_exchanger"),
    ("cooler",        "heat_exchanger"),
    ("heater",        "heat_exchanger"),
    ("spray nozzle",  "nozzle"),
    ("spray_nozzle",  "nozzle"),
    ("manhole",       "apparatus_element"),
    ("support",       "apparatus_element"),
    ("socket",        "nozzle"),
    ("vent",          "piping"),
]

# Regex patterns

# Files that are reference sheets / full drawings — not individual symbols
_REFERENCE_SHEET_PATTERNS: list[str] = [
    r"symbols\s+sheet\s+\d",
    r"symbols\s+iso",
    r"p&id\s+x\d",
    r"p&id\s+drawing",
]
_REFERENCE_RE = re.compile(
    "|".join(_REFERENCE_SHEET_PATTERNS), re.IGNORECASE
)

# Pattern to extract standard from filename: "(ISO 10628-2)" or "(DIN 2429)"
_STANDARD_RE = re.compile(r'\(\s*((?:ISO|DIN|ISA)\s*[\d\-]+(?:-\d+)?)\s*\)', re.IGNORECASE)

# SVG category sets

# Valve-like categories: horizontal in/out connection geometry
_VALVE_CATS: frozenset[str] = frozenset({
    "valve", "check_valve", "relief_valve", "control_valve", "regulator", "safety",
})
# Categories whose connection geometry is best found via open-end stub detection
_OPEN_END_CATS: frozenset[str] = _VALVE_CATS | frozenset({
    "pump", "compressor", "pipe", "fitting", "connection", "piping", "line_type",
})
# Categories rendered as instrument bubbles (circle → cardinal points)
_BUBBLE_CATS: frozenset[str] = frozenset({"instrument_bubble", "instrument", "annotation"})
# Categories whose connection geometry is top/bottom (process/signal)
_ACTUATOR_CATS: frozenset[str] = frozenset({"actuator", "fail_position"})

# Metadata / path constants

# Categories that belong under processed/pip/ regardless of standard
PIP_CATEGORIES: frozenset[str] = frozenset({"piping", "line_type", "pipe"})

# Filename prefixes that identify PIP (Process Industry Practices) standard symbols
PIPING_STEM_PREFIXES: tuple[str, ...] = ("pip_", "pipa_")

# SVG minification

# Ordered list of (compiled regex, replacement) for SVG minification
_MINIFY_PATTERNS: list[tuple[re.Pattern, str]] = [
    # XML declaration
    (re.compile(r'<\?xml[^?]*\?>\s*\n?'), ''),
    # DOCTYPE declaration (handles quoted system identifiers)
    (re.compile(r'<!DOCTYPE[^[>]*(?:\[[^\]]*\])?\s*>\s*\n?', re.DOTALL), ''),
    # <metadata>...</metadata> block
    (re.compile(r'\s*<metadata\b[^>]*>.*?</metadata>\s*', re.DOTALL), '\n'),
    # Inkscape / sodipodi self-closing elements
    (re.compile(r'\s*<(?:sodipodi|inkscape):[^\s>][^/]*/>\s*', re.DOTALL), ''),
    # Inkscape / sodipodi block elements
    (re.compile(
        r'\s*<(sodipodi|inkscape):[^\s>][^>]*>.*?</\1:[^>]*>\s*', re.DOTALL
    ), ''),
    # Collapse 3+ consecutive blank lines to one
    (re.compile(r'\n{3,}'), '\n\n'),
]
