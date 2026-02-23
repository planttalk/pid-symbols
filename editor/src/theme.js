import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary:    { main: '#0e9ef7' },
    secondary:  { main: '#9cdcfe' },
    success:    { main: '#4ec994' },
    warning:    { main: '#FF9800' },
    error:      { main: '#F44336' },
    background: { default: '#1e1e1e', paper: '#252525' },
  },
  typography: {
    fontFamily: "'Consolas', 'Courier New', monospace",
    fontSize:   12,
    h6:         { fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.5px', color: '#9cdcfe' },
  },
  components: {
    MuiButton: {
      defaultProps:  { size: 'small', variant: 'outlined' },
      styleOverrides: {
        root: { fontFamily: "'Consolas', 'Courier New', monospace", fontSize: 11, textTransform: 'none', minWidth: 0 },
      },
    },
    MuiTextField: {
      defaultProps: { size: 'small', variant: 'outlined' },
      styleOverrides: {
        root: { '& input': { fontFamily: "'Consolas', 'Courier New', monospace", fontSize: 12 } },
      },
    },
    MuiSelect: {
      defaultProps: { size: 'small' },
    },
    MuiChip: {
      defaultProps: { size: 'small' },
    },
    MuiDivider: {
      styleOverrides: { root: { borderColor: '#3c3c3c', margin: '6px 0' } },
    },
    MuiAccordion: {
      styleOverrides: {
        root: {
          background: '#1e1e1e',
          border:     '1px solid #333',
          boxShadow:  'none',
          '&:before': { display: 'none' },
          '&.Mui-expanded': { margin: 0 },
        },
      },
    },
    MuiAccordionSummary: {
      styleOverrides: {
        root:    { minHeight: 32, padding: '0 8px', '&.Mui-expanded': { minHeight: 32 } },
        content: { margin: '4px 0', '&.Mui-expanded': { margin: '4px 0' } },
      },
    },
    MuiAccordionDetails: {
      styleOverrides: { root: { padding: '2px 8px 6px' } },
    },
    MuiSlider: {
      styleOverrides: {
        root:  { padding: '8px 0', height: 3 },
        thumb: { width: 10, height: 10 },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: { padding: '2px 8px', borderRadius: 2 },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          fontFamily: "'Consolas', 'Courier New', monospace",
          fontSize:   11,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          minHeight:  36,
          padding:    '4px 12px',
        },
      },
    },
  },
});

export default theme;
