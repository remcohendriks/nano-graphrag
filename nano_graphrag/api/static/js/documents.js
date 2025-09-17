// Document upload module

const Documents = {
    fileContents: [],

    init() {
        // Set up file input handler
        const fileInput = document.getElementById('fileInput');
        if (fileInput) {
            fileInput.addEventListener('change', (e) => this.handleFileSelection(e));
        }

        // Set up upload button handler
        const uploadButton = document.getElementById('uploadButton');
        if (uploadButton) {
            uploadButton.addEventListener('click', () => this.uploadFiles());
        }
    },

    async handleFileSelection(e) {
        const files = Array.from(e.target.files);
        const fileListDiv = document.getElementById('fileList');
        const uploadButton = document.getElementById('uploadButton');

        fileListDiv.innerHTML = '';
        this.fileContents = [];

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
            fileSize.textContent = Utils.formatFileSize(file.size);

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
                    this.updateUploadButton();
                };
                fileItem.appendChild(removeBtn);
            } else {
                // Read valid files
                const reader = new FileReader();
                reader.onload = (e) => {
                    this.fileContents.push(e.target.result);
                    this.updateUploadButton();
                };
                reader.readAsText(file);
            }

            fileListDiv.appendChild(fileItem);
        }

        this.updateUploadButton();
    },

    updateUploadButton() {
        const uploadButton = document.getElementById('uploadButton');
        const validFiles = document.querySelectorAll('.file-item:not(.invalid)').length;
        uploadButton.disabled = validFiles === 0 || this.fileContents.length !== validFiles;
    },

    async uploadFiles() {
        const uploadStatus = document.getElementById('uploadStatus');

        try {
            const documents = this.fileContents.map(content => ({ content }));

            const response = await Utils.apiRequest('/api/v1/documents/batch', {
                method: 'POST',
                body: JSON.stringify({ documents })
            });

            const result = await response.json();
            uploadStatus.className = 'success';
            uploadStatus.textContent = `Upload successful! Job ID: ${result.job_id}`;
            uploadStatus.style.display = 'block';

            // Clear file input
            document.getElementById('fileInput').value = '';
            document.getElementById('fileList').innerHTML = '';
            this.fileContents = [];
            this.updateUploadButton();

            // Switch to jobs tab to show progress
            if (window.Tabs) {
                window.Tabs.switchTab('jobs');
            }

            // Refresh job list
            if (window.Jobs) {
                await window.Jobs.loadJobs();
            }
        } catch (err) {
            uploadStatus.className = 'error';
            uploadStatus.textContent = `Upload failed: ${err.message}`;
            uploadStatus.style.display = 'block';
        }

        // Hide status message after 5 seconds
        setTimeout(() => {
            uploadStatus.style.display = 'none';
        }, 5000);
    }
};

// Export for use
window.Documents = Documents;