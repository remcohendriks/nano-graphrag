// Jobs monitoring module

const Jobs = {
    autoRefreshEnabled: true,
    refreshInterval: null,

    init() {
        // Set up refresh button
        const refreshButton = document.getElementById('refreshButton');
        if (refreshButton) {
            refreshButton.addEventListener('click', () => this.loadJobs());
        }

        // Set up auto-refresh checkbox
        const autoRefreshCheckbox = document.getElementById('autoRefresh');
        if (autoRefreshCheckbox) {
            autoRefreshCheckbox.addEventListener('change', (e) => {
                this.autoRefreshEnabled = e.target.checked;
                if (this.autoRefreshEnabled) {
                    this.startAutoRefresh();
                } else {
                    this.stopAutoRefresh();
                }
            });
        }

        // Start auto-refresh if enabled
        if (this.autoRefreshEnabled) {
            this.startAutoRefresh();
        }

        // Initial load
        this.loadJobs();
    },

    onTabActivated() {
        // Refresh when tab is activated
        this.loadJobs();

        // Restart auto-refresh if enabled
        if (this.autoRefreshEnabled) {
            this.startAutoRefresh();
        }
    },

    async loadJobs() {
        try {
            const response = await fetch('/api/v1/jobs/?limit=50');
            const jobs = await response.json();

            const tbody = document.getElementById('jobsBody');
            tbody.innerHTML = '';

            jobs.forEach(job => {
                const row = tbody.insertRow();

                // Job ID (truncated)
                row.insertCell(0).textContent = job.job_id.slice(0, 8);

                // Status
                const statusCell = row.insertCell(1);
                const statusSpan = document.createElement('span');
                statusSpan.className = `status ${job.status}`;
                statusSpan.textContent = job.status;
                statusCell.appendChild(statusSpan);

                // Progress
                const progressCell = row.insertCell(2);
                if (job.status === 'processing') {
                    const progressBar = document.createElement('div');
                    progressBar.className = 'progress-bar';

                    const fill = document.createElement('div');
                    fill.className = 'progress-fill';
                    const percentage = job.progress.total > 0
                        ? (job.progress.current / job.progress.total) * 100
                        : 0;
                    fill.style.width = `${percentage}%`;

                    const text = document.createElement('div');
                    text.className = 'progress-text';
                    text.textContent = `${job.progress.current}/${job.progress.total} - ${job.progress.phase}`;

                    progressBar.appendChild(fill);
                    progressBar.appendChild(text);
                    progressCell.appendChild(progressBar);
                } else {
                    progressCell.textContent = `${job.progress.current}/${job.progress.total}`;
                }

                // Documents
                row.insertCell(3).textContent = job.doc_ids.length;

                // Created
                const created = new Date(job.created_at);
                row.insertCell(4).textContent = created.toLocaleString();

                // Duration
                const durationCell = row.insertCell(5);
                if (job.completed_at) {
                    const duration = new Date(job.completed_at) - created;
                    durationCell.textContent = Utils.formatDuration(duration);
                } else if (job.status === 'processing') {
                    const elapsed = Date.now() - created;
                    durationCell.textContent = Utils.formatDuration(elapsed);
                } else {
                    durationCell.textContent = '-';
                }
            });

            Utils.updateStatus(`Found ${jobs.length} jobs`);

        } catch (error) {
            Utils.updateStatus(`Error loading jobs: ${error.message}`);
        }
    },

    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        this.refreshInterval = setInterval(() => {
            // Only refresh if on the jobs tab
            if (window.Tabs && window.Tabs.currentTab === 'jobs') {
                this.loadJobs();
            }
        }, 3000);
    },

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
};

// Export for use
window.Jobs = Jobs;