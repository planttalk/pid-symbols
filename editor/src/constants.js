'use strict';

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
