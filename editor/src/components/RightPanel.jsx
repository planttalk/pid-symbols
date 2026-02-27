import { Box, Tabs, Tab } from '@mui/material';
import TuneIcon from '@mui/icons-material/Tune';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import FlagIcon from '@mui/icons-material/Flag';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import CloudIcon from '@mui/icons-material/Cloud';
import { useEditorStore } from '../store';
import PortsTab from './PortsTab';
import AugmentTab from './AugmentTab';
import ReportsTab from './ReportsTab';
import ExportTab from './ExportTab';
import CloudTab from './CloudTab';

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
              minHeight: 28,
              '& .MuiTabs-flexContainer': { gap: '2px' },
              '& .MuiTabs-indicator': { display: 'none' },
              '& .MuiTab-root': {
                flex: 1, minHeight: 28, minWidth: 0,
                py: '4px', px: '6px',
                fontSize: 10, gap: '3px',
                borderRadius: '5px',
                transition: 'background 0.15s ease',
                textTransform: 'none',
              },
            }}
          >
            <Tab
              label="Ports"
              icon={<TuneIcon sx={{ fontSize: 12 }} />}
              iconPosition="start"
              sx={{ '&.Mui-selected': { bgcolor: 'rgba(129,140,248,0.18)', color: 'primary.main' } }}
            />
            <Tab
              label="Augment"
              icon={<AutoFixHighIcon sx={{ fontSize: 12 }} />}
              iconPosition="start"
              sx={{ '&.Mui-selected': { bgcolor: 'rgba(129,140,248,0.18)', color: 'primary.main' } }}
            />
            <Tab
              label="Reports"
              icon={<FlagIcon sx={{ fontSize: 12 }} />}
              iconPosition="start"
              sx={{ '&.Mui-selected': { bgcolor: 'rgba(239,68,68,0.15)', color: '#ef4444' } }}
            />
            <Tab
              label="Export"
              icon={<SaveAltIcon sx={{ fontSize: 12 }} />}
              iconPosition="start"
              sx={{ '&.Mui-selected': { bgcolor: 'rgba(156,68,238,0.15)', color: '#cc88ff' } }}
            />
            <Tab
              label="Cloud"
              icon={<CloudIcon sx={{ fontSize: 12 }} />}
              iconPosition="start"
              sx={{ '&.Mui-selected': { bgcolor: 'rgba(0,188,212,0.12)', color: '#00bcd4' } }}
            />
          </Tabs>
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {activeTab === 0 && <PortsTab />}
        {activeTab === 1 && <AugmentTab />}
        {activeTab === 2 && <ReportsTab />}
        {activeTab === 3 && <ExportTab />}
        {activeTab === 4 && <CloudTab />}
      </Box>
    </Box>
  );
}
