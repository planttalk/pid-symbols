export const PORT_TYPES = [
  { id: 'in',        label: 'In',        color: '#2196F3' },
  { id: 'out',       label: 'Out',       color: '#F44336' },
  { id: 'in_out',    label: 'In/Out',    color: '#009688' },
  { id: 'signal',    label: 'Signal',    color: '#9C27B0' },
  { id: 'process',   label: 'Process',   color: '#FF9800' },
  { id: 'north',     label: 'North',     color: '#4CAF50' },
  { id: 'south',     label: 'South',     color: '#4CAF50' },
  { id: 'east',      label: 'East',      color: '#4CAF50' },
  { id: 'west',      label: 'West',      color: '#4CAF50' },
  { id: 'reference', label: 'Ref.',      color: '#9E9E9E' },
  { id: 'custom',    label: 'Custom',    color: '#607D8B' },
];

// Set of all known type ids (used for migration of old single-field snap_points)
export const KNOWN_TYPES = new Set(PORT_TYPES.map(t => t.id));

export const TYPE_COLOR = Object.fromEntries(PORT_TYPES.map(t => [t.id, t.color]));

export function portColor(id) {
  return TYPE_COLOR[(id || '').toLowerCase()] ?? '#607D8B';
}

export const NS = 'http://www.w3.org/2000/svg';

export const EFFECT_GROUPS = [
  {
    label: 'Physical',
    effects: [
      { name: 'yellowing',      label: 'Yellowing'      },
      { name: 'foxing',         label: 'Foxing'         },
      { name: 'crease',         label: 'Crease'         },
      { name: 'water_stain',    label: 'Water Stain'    },
      { name: 'edge_wear',      label: 'Edge Wear'      },
      { name: 'fingerprint',    label: 'Fingerprint'    },
      { name: 'binding_shadow', label: 'Binding Shadow' },
      { name: 'bleed_through',  label: 'Bleed Through'  },
      { name: 'hole_punch',     label: 'Hole Punch'     },
      { name: 'tape_residue',   label: 'Tape Residue'   },
    ],
  },
  {
    label: 'Chemical',
    effects: [
      { name: 'ink_fading',    label: 'Ink Fading'    },
      { name: 'ink_bleed',     label: 'Ink Bleed'     },
      { name: 'coffee_stain',  label: 'Coffee Stain'  },
      { name: 'oil_stain',     label: 'Oil Stain'     },
      { name: 'acid_spots',    label: 'Acid Spots'    },
      { name: 'bleaching',     label: 'Bleaching'     },
      { name: 'toner_flaking', label: 'Toner Flaking' },
    ],
  },
  {
    label: 'Biological',
    effects: [
      { name: 'mold',          label: 'Mold'          },
      { name: 'mildew',        label: 'Mildew'        },
      { name: 'bio_foxing',    label: 'Bio Foxing'    },
      { name: 'insect_damage', label: 'Insect Damage' },
    ],
  },
  {
    label: 'Scanning',
    effects: [
      { name: 'noise',             label: 'Noise'             },
      { name: 'salt_pepper',       label: 'Salt & Pepper'     },
      { name: 'vignette',          label: 'Vignette'          },
      { name: 'jpeg_artifacts',    label: 'JPEG Artifacts'    },
      { name: 'skew',              label: 'Skew'              },
      { name: 'barrel_distortion', label: 'Barrel Distortion' },
      { name: 'moire',             label: 'Moiré'             },
      { name: 'halftone',          label: 'Halftone'          },
      { name: 'color_cast',        label: 'Color Cast'        },
      { name: 'blur',              label: 'Blur'              },
      { name: 'dust',              label: 'Dust'              },
      { name: 'overexpose',        label: 'Overexpose'        },
      { name: 'underexpose',       label: 'Underexpose'       },
      { name: 'motion_streak',     label: 'Motion Streak'     },
      { name: 'binarization',      label: 'Binarization'      },
      { name: 'pixelation',        label: 'Pixelation'        },
    ],
  },
];

export const ALL_EFFECT_NAMES = EFFECT_GROUPS.flatMap(g => g.effects.map(e => e.name));
