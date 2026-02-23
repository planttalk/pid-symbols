import { Box, Tabs, Tab } from '@mui/material';
import { useEditorStore } from '../store';
import PortsTab from './PortsTab';
import AugmentTab from './AugmentTab';

export default function RightPanel() {
  const { activeTab, setActiveTab, currentPath, previewAugment } = useEditorStore();

  const handleTabChange = (_, newVal) => {
    setActiveTab(newVal);
    if (newVal === 1 && currentPath) {
      // Auto-preview when switching to Augment tab
      previewAugment?.();
    }
  };

  return (
    <Box sx={{
      width: 300,
      borderLeft: '1px solid #444',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <Tabs
        value={activeTab}
        onChange={handleTabChange}
        sx={{
          flexShrink: 0,
          borderBottom: '1px solid #444',
          minHeight: 36,
          '& .MuiTabs-indicator': { bgcolor: 'secondary.main' },
        }}
      >
        <Tab label="Ports"   sx={{ flex: 1 }} />
        <Tab label="Augment" sx={{ flex: 1 }} />
      </Tabs>

      <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {activeTab === 0 && <PortsTab />}
        {activeTab === 1 && <AugmentTab />}
      </Box>
    </Box>
  );
}
