import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary:   { main: '#818cf8' },
    secondary: { main: '#38bdf8' },
    success:   { main: '#34d399' },
    warning:   { main: '#fb923c' },
    error:     { main: '#fb7185' },
    background: {
      default: '#0f0f14',
      paper:   '#16161e',
    },
    text: {
      primary:   'rgba(255,255,255,0.90)',
      secondary: 'rgba(255,255,255,0.50)',
      disabled:  'rgba(255,255,255,0.25)',
    },
    divider: 'rgba(255,255,255,0.07)',
  },

  typography: {
    fontFamily: '"Inter", "Segoe UI", system-ui, sans-serif',
    fontSize: 13,
    h6: {
      fontSize: '0.7rem',
      fontWeight: 700,
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      color: 'rgba(255,255,255,0.25)',
    },
  },

  shape: {
    borderRadius: 8,
  },

  components: {
    // ── Global scrollbar CSS ─────────────────────────────────────────────────
    MuiCssBaseline: {
      styleOverrides: `
        *, *::before, *::after {
          box-sizing: border-box;
        }
        ::-webkit-scrollbar {
          width: 5px;
          height: 5px;
        }
        ::-webkit-scrollbar-track {
          background: transparent;
        }
        ::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.10);
          border-radius: 999px;
        }
        ::-webkit-scrollbar-thumb:hover {
          background: rgba(255,255,255,0.20);
        }
        * {
          scrollbar-width: thin;
          scrollbar-color: rgba(255,255,255,0.10) transparent;
        }
        body {
          font-family: "Inter", "Segoe UI", system-ui, sans-serif;
          background: #0f0f14;
        }
      `,
    },

    // ── Button ───────────────────────────────────────────────────────────────
    MuiButton: {
      defaultProps: { size: 'small', variant: 'outlined' },
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 500,
          fontSize: '0.73rem',
          borderRadius: '6px',
          minWidth: 0,
          fontFamily: '"Inter", "Segoe UI", system-ui, sans-serif',
        },
      },
    },

    // ── TextField ────────────────────────────────────────────────────────────
    MuiTextField: {
      defaultProps: { size: 'small', variant: 'outlined' },
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            '& fieldset': {
              borderColor: 'rgba(255,255,255,0.08)',
              transition: 'border-color 0.15s ease',
            },
            '&:hover fieldset': {
              borderColor: 'rgba(255,255,255,0.15)',
            },
            '&.Mui-focused fieldset': {
              borderColor: '#818cf8',
              borderWidth: 1,
            },
          },
        },
      },
    },

    // ── Select ───────────────────────────────────────────────────────────────
    MuiSelect: {
      defaultProps: { size: 'small' },
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(255,255,255,0.08)',
            transition: 'border-color 0.15s ease',
          },
          '&:hover .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(255,255,255,0.15)',
          },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: '#818cf8',
            borderWidth: 1,
          },
        },
      },
    },

    // ── Accordion ────────────────────────────────────────────────────────────
    MuiAccordion: {
      styleOverrides: {
        root: {
          background: 'rgba(255,255,255,0.025)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: '8px !important',
          boxShadow: 'none',
          '&::before': { display: 'none' },
          '&.Mui-expanded': { margin: 0 },
        },
      },
    },

    // ── AccordionSummary ─────────────────────────────────────────────────────
    MuiAccordionSummary: {
      styleOverrides: {
        root: {
          minHeight: 36,
          padding: '0 10px',
          borderRadius: '8px',
          '&.Mui-expanded': { minHeight: 36 },
        },
        content: {
          margin: '6px 0',
          alignItems: 'center',
          '&.Mui-expanded': { margin: '6px 0' },
        },
      },
    },

    // ── AccordionDetails ─────────────────────────────────────────────────────
    MuiAccordionDetails: {
      styleOverrides: {
        root: { padding: '4px 10px 8px' },
      },
    },

    // ── Slider ───────────────────────────────────────────────────────────────
    MuiSlider: {
      styleOverrides: {
        root: { padding: '8px 0', height: 3 },
        thumb: {
          width: 11,
          height: 11,
          '&:hover, &.Mui-focusVisible': {
            boxShadow: '0 0 0 6px rgba(129,140,248,0.18)',
          },
        },
        track: { border: 'none' },
        rail:  { opacity: 0.25 },
      },
    },

    // ── Checkbox ─────────────────────────────────────────────────────────────
    MuiCheckbox: {
      styleOverrides: {
        root: {
          color: 'rgba(255,255,255,0.25)',
          '&.Mui-checked': { color: '#818cf8' },
          '&:hover': { background: 'rgba(129,140,248,0.08)' },
        },
      },
    },

    // ── ListItemButton ───────────────────────────────────────────────────────
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: '6px',
          transition: 'background 0.12s ease',
          '&.Mui-selected': {
            backgroundColor: 'rgba(129,140,248,0.15)',
            '&:hover': { backgroundColor: 'rgba(129,140,248,0.20)' },
          },
          '&:hover': {
            backgroundColor: 'rgba(255,255,255,0.05)',
          },
        },
      },
    },

    // ── Tab ──────────────────────────────────────────────────────────────────
    MuiTab: {
      styleOverrides: {
        root: {
          fontFamily: '"Inter", "Segoe UI", system-ui, sans-serif',
          fontSize: '0.73rem',
          fontWeight: 500,
          textTransform: 'none',
          minHeight: 32,
          padding: '4px 12px',
          borderRadius: '6px',
          color: 'rgba(255,255,255,0.50)',
          '&.Mui-selected': { color: 'rgba(255,255,255,0.90)' },
        },
      },
    },

    // ── Tabs ─────────────────────────────────────────────────────────────────
    MuiTabs: {
      styleOverrides: {
        root: { minHeight: 36 },
        indicator: { backgroundColor: '#818cf8', height: 2, borderRadius: '999px' },
      },
    },

    // ── Alert ────────────────────────────────────────────────────────────────
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
          fontSize: '0.73rem',
          alignItems: 'center',
        },
        standardSuccess: { backgroundColor: 'rgba(52,211,153,0.12)', color: '#34d399' },
        standardError:   { backgroundColor: 'rgba(251,113,133,0.12)', color: '#fb7185' },
        standardWarning: { backgroundColor: 'rgba(251,146,60,0.12)',  color: '#fb923c' },
        standardInfo:    { backgroundColor: 'rgba(56,189,248,0.12)',  color: '#38bdf8' },
      },
    },

    // ── Chip ─────────────────────────────────────────────────────────────────
    MuiChip: {
      defaultProps: { size: 'small' },
      styleOverrides: {
        root: {
          borderRadius: '6px',
          fontSize: '0.68rem',
          fontWeight: 500,
          height: 20,
        },
      },
    },

    // ── LinearProgress ───────────────────────────────────────────────────────
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: '999px',
          height: 3,
          backgroundColor: 'rgba(255,255,255,0.08)',
        },
        bar: { borderRadius: '999px' },
      },
    },

    // ── IconButton ───────────────────────────────────────────────────────────
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: '6px',
          transition: 'background 0.12s ease',
          '&:hover': { backgroundColor: 'rgba(255,255,255,0.07)' },
        },
        sizeSmall: { padding: 4 },
      },
    },

    // ── Switch ───────────────────────────────────────────────────────────────
    MuiSwitch: {
      styleOverrides: {
        root: { padding: 6 },
        switchBase: {
          '&.Mui-checked': {
            color: '#818cf8',
            '& + .MuiSwitch-track': { backgroundColor: '#818cf8', opacity: 0.5 },
          },
        },
        track: { borderRadius: '999px', backgroundColor: 'rgba(255,255,255,0.15)', opacity: 1 },
        thumb: { width: 14, height: 14, boxShadow: 'none' },
      },
    },

    // ── Divider ──────────────────────────────────────────────────────────────
    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: 'rgba(255,255,255,0.07)',
          margin: '8px 0',
        },
      },
    },

    // ── Radio ────────────────────────────────────────────────────────────────
    MuiRadio: {
      styleOverrides: {
        root: {
          color: 'rgba(255,255,255,0.25)',
          '&.Mui-checked': { color: '#818cf8' },
          '&:hover': { background: 'rgba(129,140,248,0.08)' },
          padding: '3px 6px',
        },
      },
    },
  },
});

export default theme;
