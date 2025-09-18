// Tab navigation module

const Tabs = {
    currentTab: 'documents',

    init() {
        // Set up tab navigation event listeners
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                const tabName = e.target.dataset.tab;
                this.switchTab(tabName);
            });
        });

        // Handle URL hash for deep linking
        if (window.location.hash) {
            const tab = window.location.hash.substring(1);
            if (['documents', 'search', 'jobs'].includes(tab)) {
                this.switchTab(tab);
            }
        }

        // Listen for hash changes
        window.addEventListener('hashchange', () => {
            const tab = window.location.hash.substring(1);
            if (['documents', 'search', 'jobs'].includes(tab)) {
                this.switchTab(tab);
            }
        });
    },

    switchTab(tabName) {
        // Don't switch if already on this tab
        if (this.currentTab === tabName) {
            return;
        }

        // Update tab buttons
        document.querySelectorAll('.tab-button').forEach(button => {
            if (button.dataset.tab === tabName) {
                button.classList.add('active');
            } else {
                button.classList.remove('active');
            }
        });

        // Update tab panels
        document.querySelectorAll('.tab-panel').forEach(panel => {
            panel.classList.remove('active');
        });

        const targetPanel = document.getElementById(`${tabName}-tab`);
        if (targetPanel) {
            targetPanel.classList.add('active');
        }

        // Update current tab
        this.currentTab = tabName;

        // Update URL hash
        window.location.hash = tabName;

        // Trigger custom event for other modules to listen to
        window.dispatchEvent(new CustomEvent('tabChanged', {
            detail: { tab: tabName }
        }));

        // Tab-specific initialization
        switch (tabName) {
            case 'documents':
                // Documents tab is always ready
                break;
            case 'search':
                if (window.Search) {
                    window.Search.onTabActivated();
                }
                break;
            case 'jobs':
                if (window.Jobs) {
                    window.Jobs.onTabActivated();
                }
                break;
        }
    }
};

// Export for use
window.Tabs = Tabs;