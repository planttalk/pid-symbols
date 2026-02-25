import { Box, Tabs, Tab } from '@mui/material';
import TuneIcon from '@mui/icons-material/Tune';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import FlagIcon from '@mui/icons-material/Flag';
import { useEditorStore } from '../store';
import PortsTab from './PortsTab';
import AugmentTab from './AugmentTab';
import ReportsTab from './ReportsTab';

export default function RightPanel() {
  const { activeTab, setActiveTab, currentPath, previewAugment } = useEditorStore();

  const handleTabChange = (_, newVal) => {
    setActiveTab(newVal);
    if (newVal === 1 && currentPath) {
      previewAugment?.();
    }
  };

  return (
    <Box sx={{
      width: 300,
      borderLeft: '1px solid rgba(255,255,255,0.07)',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      bgcolor: 'background.paper',
    }}>
      {/* Tab bar */}
      <Box sx={{
        bgcolor: 'background.paper',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        flexShrink: 0,
      }}>
        {/* Segmented control wrapper */}
        <Box sx={{
          bgcolor: 'rgba(255,255,255,0.04)',
          borderRadius: '8px',
          m: 1,
          p: '3px',
          display: 'flex',
        }}>
          <Tabs
            value={activeTab}
            onChange={handleTabChange}
            sx={{
              flex: 1,
              minHeight: 32,
              '& .MuiTabs-flexContainer': { gap: '2px' },
              '& .MuiTabs-indicator': { display: 'none' },
            }}
          >
            <Tab
              label="Ports"
              icon={<TuneIcon sx={{ fontSize: 13 }} />}
              iconPosition="start"
              sx={{
                flex: 1,
                minHeight: 32,
                py: 0.5,
                px: 1,
                borderRadius: '6px',
                gap: 0.5,
                transition: 'background 0.15s ease',
                '&.Mui-selected': {
                  bgcolor: 'rgba(129,140,248,0.18)',
                  color: 'primary.main',
                },
              }}
            />
            <Tab
              label="Augment"
              icon={<AutoFixHighIcon sx={{ fontSize: 13 }} />}
              iconPosition="start"
              sx={{
                flex: 1,
                minHeight: 32,
                py: 0.5,
                px: 1,
                borderRadius: '6px',
                gap: 0.5,
                transition: 'background 0.15s ease',
                '&.Mui-selected': {
                  bgcolor: 'rgba(129,140,248,0.18)',
                  color: 'primary.main',
                },
              }}
            />
            <Tab
              label="Reports"
              icon={<FlagIcon sx={{ fontSize: 13 }} />}
              iconPosition="start"
              sx={{
                flex: 1,
                minHeight: 32,
                py: 0.5,
                px: 1,
                borderRadius: '6px',
                gap: 0.5,
                transition: 'background 0.15s ease',
                '&.Mui-selected': {
                  bgcolor: 'rgba(239,68,68,0.15)',
                  color: '#ef4444',
                },
              }}
            />
          </Tabs>
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {activeTab === 0 && <PortsTab />}
        {activeTab === 1 && <AugmentTab />}
        {activeTab === 2 && <ReportsTab />}
      </Box>
    </Box>
  );
}
