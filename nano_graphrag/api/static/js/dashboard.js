// Main dashboard initialization

document.addEventListener('DOMContentLoaded', () => {
    // Initialize all modules
    if (window.Tabs) {
        window.Tabs.init();
    }

    if (window.Documents) {
        window.Documents.init();
    }

    if (window.Search) {
        window.Search.init();
    }

    if (window.Jobs) {
        window.Jobs.init();
    }

    if (window.Backups) {
        window.Backups.init();
    }

    // Log successful initialization
    console.log('nano-graphrag dashboard initialized');
});