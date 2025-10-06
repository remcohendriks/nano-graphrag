// Backups management module

const Backups = {
    init() {
        // Create backup button
        const createBackupButton = document.getElementById('createBackupButton');
        if (createBackupButton) {
            createBackupButton.addEventListener('click', () => this.createBackup());
        }

        // Restore backup button and file input
        const backupFileInput = document.getElementById('backupFileInput');
        const restoreButton = document.getElementById('restoreButton');

        if (backupFileInput) {
            backupFileInput.addEventListener('change', (e) => {
                if (restoreButton) {
                    restoreButton.disabled = !e.target.files.length;
                }
            });
        }

        if (restoreButton) {
            restoreButton.addEventListener('click', () => this.restoreBackup());
        }

        // Refresh backups list button
        const refreshBackupsButton = document.getElementById('refreshBackupsButton');
        if (refreshBackupsButton) {
            refreshBackupsButton.addEventListener('click', () => this.loadBackups());
        }

        // Initial load
        this.loadBackups();
    },

    onTabActivated() {
        // Refresh when tab is activated
        this.loadBackups();
    },

    async createBackup() {
        const statusDiv = document.getElementById('backupStatus');
        const createButton = document.getElementById('createBackupButton');

        try {
            createButton.disabled = true;
            statusDiv.textContent = 'Creating backup...';
            statusDiv.className = 'status-message info';

            const response = await fetch('/api/v1/backup', {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            statusDiv.textContent = `Backup job created: ${result.job_id}`;
            statusDiv.className = 'status-message success';

            // Refresh list after a delay to allow job to complete
            setTimeout(() => this.loadBackups(), 2000);

        } catch (error) {
            statusDiv.textContent = `Error: ${error.message}`;
            statusDiv.className = 'status-message error';
        } finally {
            createButton.disabled = false;
        }
    },

    async restoreBackup() {
        const fileInput = document.getElementById('backupFileInput');
        const statusDiv = document.getElementById('restoreStatus');
        const restoreButton = document.getElementById('restoreButton');

        const file = fileInput.files[0];
        if (!file) {
            statusDiv.textContent = 'Please select a backup file';
            statusDiv.className = 'status-message error';
            return;
        }

        if (!file.name.endsWith('.ngbak')) {
            statusDiv.textContent = 'Invalid file type. Please select a .ngbak file';
            statusDiv.className = 'status-message error';
            return;
        }

        try {
            restoreButton.disabled = true;
            statusDiv.textContent = 'Restoring backup...';
            statusDiv.className = 'status-message info';

            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/v1/backup/restore', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            const result = await response.json();

            statusDiv.textContent = `Restore job created: ${result.job_id}`;
            statusDiv.className = 'status-message success';

            // Clear file input
            fileInput.value = '';
            restoreButton.disabled = true;

        } catch (error) {
            statusDiv.textContent = `Error: ${error.message}`;
            statusDiv.className = 'status-message error';
            restoreButton.disabled = false;
        }
    },

    async loadBackups() {
        const statusDiv = document.getElementById('backupsListStatus');
        const tbody = document.getElementById('backupsBody');

        try {
            statusDiv.textContent = 'Loading backups...';

            const response = await fetch('/api/v1/backup');

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const backups = await response.json();

            statusDiv.textContent = '';

            if (backups.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">No backups found</td></tr>';
                return;
            }

            tbody.innerHTML = backups.map(backup => `
                <tr>
                    <td>${this.escapeHtml(backup.backup_id)}</td>
                    <td>${this.formatDate(backup.created_at)}</td>
                    <td>${this.formatSize(backup.size_bytes)}</td>
                    <td>${this.formatBackends(backup.backends)}</td>
                    <td>
                        <button class="download-btn" onclick="Backups.downloadBackup('${this.escapeHtml(backup.backup_id)}')">Download</button>
                        <button class="delete-btn" onclick="Backups.deleteBackup('${this.escapeHtml(backup.backup_id)}')">Delete</button>
                    </td>
                </tr>
            `).join('');

        } catch (error) {
            statusDiv.textContent = `Error: ${error.message}`;
            statusDiv.className = 'status-message error';
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Failed to load backups</td></tr>';
        }
    },

    async downloadBackup(backupId) {
        try {
            const response = await fetch(`/api/v1/backup/${encodeURIComponent(backupId)}/download`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Create download link
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${backupId}.ngbak`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

        } catch (error) {
            alert(`Download failed: ${error.message}`);
        }
    },

    async deleteBackup(backupId) {
        if (!confirm(`Are you sure you want to delete backup "${backupId}"?`)) {
            return;
        }

        try {
            const response = await fetch(`/api/v1/backup/${encodeURIComponent(backupId)}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            // Refresh list
            this.loadBackups();

        } catch (error) {
            alert(`Delete failed: ${error.message}`);
        }
    },

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString();
    },

    formatSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    },

    formatBackends(backends) {
        return Object.entries(backends)
            .map(([key, value]) => `${key}: ${value}`)
            .join(', ');
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// Export for use
window.Backups = Backups;
