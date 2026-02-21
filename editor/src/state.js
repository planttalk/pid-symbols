'use strict';

/**
 * Central mutable state for the port editor.
 * All modules import this object and access state via state.xxx.
 * Never destructure — always access as state.ports, state.selIdx, etc.
 * so mutations are visible across modules.
 */
export const state = {
  allSymbols:     [],     // [{path, name, standard, category}] — full list
  visibleSymbols: [],     // currently shown (filtered) symbols
  currentPath:    null,
  symbolMeta:     null,
  ports:          [],     // [{id, type, x, y}] or [{id, type, zone: {...}}]

  selection:  new Set(),  // set of selected port indices
  selIdx:     null,       // primary selected port index

  drag:       null,       // {idx} while dragging a point port
  zoneDrag:   null,       // {idx, mode, startPt, startZone} while zone-dragging

  matchMode:  null,       // null | 'Y' | 'X'

  // Midpoint state machine:
  //   null                          → idle
  //   { step: 1 }                   → waiting for first reference port
  //   { step: 2, a }                → first ref picked, waiting for second
  //   { step: 3, a, b, px, py }    → both refs picked, preview shown
  midState:   null,

  activeType: 'in',       // type applied to newly created ports

  // Current symbol viewBox dimensions
  vw: 80,
  vh: 80,

  // Port visual sizing (recomputed on symbol load)
  portR:    3,
  labelSz:  3.3,

  // Pixel size at fit-to-window (min zoom bound)
  initSvgW: 480,
  initSvgH: 480,
};
