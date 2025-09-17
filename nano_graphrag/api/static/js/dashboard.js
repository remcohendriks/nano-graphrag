// Job Dashboard JavaScript
let autoRefreshEnabled = true;
let refreshInterval;
let fileContents = [];

// File upload handling
document.getElementById('fileInput').addEventListener('change', async (e) => {
    const files = Array.from(e.target.files);
    const fileListDiv = document.getElementById('fileList');
    const uploadButton = document.getElementById('uploadButton');

    fileListDiv.innerHTML = '';
    fileContents = [];

    for (const file of files) {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';

        const isValid = file.size < 10 * 1024 * 1024; // 10MB limit
        if (!isValid) {
            fileItem.classList.add('invalid');
        }

        const fileInfo = document.createElement('span');
        fileInfo.className = 'file-info';
        fileInfo.textContent = file.name;

        const fileSize = document.createElement('span');
        fileSize.className = 'file-size';
        fileSize.textContent = formatFileSize(file.size);

        fileItem.appendChild(fileInfo);
        fileItem.appendChild(fileSize);

        if (!isValid) {
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-btn';
            removeBtn.textContent = '✕';
            removeBtn.onclick = () => {
                fileItem.remove();
                // Remove from file input
                const dt = new DataTransfer();
                const { files } = document.getElementById('fileInput');
                for (let i = 0; i < files.length; i++) {
                    if (files[i] !== file) {
                        dt.items.add(files[i]);
                    }
                }
                document.getElementById('fileInput').files = dt.files;
                updateUploadButton();
            };
            fileItem.appendChild(removeBtn);
        } else {
            // Read valid files
            const reader = new FileReader();
            reader.onload = (e) => {
                fileContents.push(e.target.result);
                updateUploadButton();
            };
            reader.readAsText(file);
        }

        fileListDiv.appendChild(fileItem);
    }

    updateUploadButton();
});

function updateUploadButton() {
    const uploadButton = document.getElementById('uploadButton');
    const validFiles = document.querySelectorAll('.file-item:not(.invalid)').length;
    uploadButton.disabled = validFiles === 0 || fileContents.length !== validFiles;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' bytes';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

document.getElementById('uploadButton').addEventListener('click', async () => {
    const uploadStatus = document.getElementById('uploadStatus');

    try {
        const documents = fileContents.map(content => ({ content }));

        const response = await fetch('/api/v1/documents/batch', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ documents })
        });

        if (response.ok) {
            const result = await response.json();
            uploadStatus.className = 'success';
            uploadStatus.textContent = `Upload successful! Job ID: ${result.job_id}`;
            uploadStatus.style.display = 'block';

            // Clear file input
            document.getElementById('fileInput').value = '';
            document.getElementById('fileList').innerHTML = '';
            fileContents = [];
            updateUploadButton();

            // Refresh job list
            await loadJobs();
        } else {
            const error = await response.json();
            uploadStatus.className = 'error';
            uploadStatus.textContent = `Upload failed: ${error.detail}`;
            uploadStatus.style.display = 'block';
        }
    } catch (err) {
        uploadStatus.className = 'error';
        uploadStatus.textContent = `Upload failed: ${err.message}`;
        uploadStatus.style.display = 'block';
    }

    setTimeout(() => {
        uploadStatus.style.display = 'none';
    }, 5000);
});

// Job monitoring
async function loadJobs() {
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
                fill.style.width = `${(job.progress.current / job.progress.total) * 100}%`;

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
                durationCell.textContent = formatDuration(duration);
            } else if (job.status === 'processing') {
                const elapsed = Date.now() - created;
                durationCell.textContent = formatDuration(elapsed);
            } else {
                durationCell.textContent = '-';
            }
        });

        updateStatus(`Found ${jobs.length} jobs`);

    } catch (error) {
        updateStatus(`Error loading jobs: ${error.message}`);
    }
}

function formatDuration(ms) {
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
}

function updateStatus(message) {
    document.getElementById('status').textContent =
        `${message} - Last updated: ${new Date().toLocaleTimeString()}`;
}

// Controls
document.getElementById('refreshButton').addEventListener('click', loadJobs);

document.getElementById('autoRefresh').addEventListener('change', (e) => {
    autoRefreshEnabled = e.target.checked;
    if (autoRefreshEnabled) {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
});

function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(loadJobs, 3000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Initialize
loadJobs();
startAutoRefresh();