// Search module

const Search = {
    searchHistory: [],
    maxHistoryItems: 10,
    isSearching: false,
    currentEventSource: null,

    init() {
        // Load search history from localStorage
        this.loadHistory();

        // Set up search button
        const searchButton = document.getElementById('searchButton');
        if (searchButton) {
            searchButton.addEventListener('click', () => this.performSearch());
        }

        // Set up enter key on search input
        const searchQuery = document.getElementById('searchQuery');
        if (searchQuery) {
            searchQuery.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !this.isSearching) {
                    this.performSearch();
                }
            });
        }

        // Set up clear history button
        const clearHistoryBtn = document.getElementById('clearHistory');
        if (clearHistoryBtn) {
            clearHistoryBtn.addEventListener('click', () => this.clearHistory());
        }

        // Render initial history
        this.renderHistory();
    },

    onTabActivated() {
        // Focus search input when tab is activated
        const searchQuery = document.getElementById('searchQuery');
        if (searchQuery) {
            searchQuery.focus();
        }
    },

    async performSearch() {
        if (this.isSearching) {
            return;
        }

        const queryInput = document.getElementById('searchQuery');
        const modeSelect = document.getElementById('queryMode');
        const searchButton = document.getElementById('searchButton');
        const resultsDiv = document.getElementById('searchResults');

        const query = queryInput.value.trim();
        const mode = modeSelect.value;

        if (!query) {
            this.showError('Please enter a search query');
            return;
        }

        // Update UI state
        this.isSearching = true;
        searchButton.disabled = true;
        searchButton.textContent = 'Searching...';

        // Clear previous results
        resultsDiv.innerHTML = '<div class="search-loading">Searching...</div>';

        // Add to history
        this.addToHistory(query, mode);

        try {
            // Use streaming endpoint for better UX
            await this.streamSearch(query, mode);
        } catch (error) {
            this.showError(`Search failed: ${error.message}`);
        } finally {
            this.isSearching = false;
            searchButton.disabled = false;
            searchButton.textContent = 'Search';
        }
    },

    async streamSearch(query, mode) {
        const resultsDiv = document.getElementById('searchResults');

        // Close any existing stream
        if (this.currentEventSource) {
            this.currentEventSource.close();
        }

        // Create results container
        resultsDiv.innerHTML = `
            <div class="result-container">
                <div class="result-header">
                    <div class="result-meta">
                        <span class="result-mode">Mode: ${mode}</span>
                        <span class="result-time" id="resultTime">Processing...</span>
                    </div>
                    <div class="result-actions">
                        <button class="copy-btn" id="copyResult" title="Copy to clipboard">📋 Copy</button>
                        <button class="export-btn" id="exportResult" title="Export">💾 Export</button>
                    </div>
                </div>
                <div class="result-content" id="resultContent"></div>
            </div>
        `;

        const resultContent = document.getElementById('resultContent');
        let fullAnswer = '';
        const startTime = Date.now();

        // Create request body
        const requestBody = {
            question: query,
            mode: mode
        };

        // Use fetch with streaming
        try {
            const response = await fetch('/api/v1/query/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        try {
                            const event = JSON.parse(data);
                            this.handleStreamEvent(event, resultContent, startTime);

                            if (event.event === 'chunk') {
                                fullAnswer += event.content;
                            }
                        } catch (e) {
                            // Ignore JSON parse errors
                        }
                    }
                }
            }
        } catch (error) {
            throw error;
        }

        // Set up copy and export buttons
        this.setupResultActions(fullAnswer, query, mode);
    },

    handleStreamEvent(event, resultContent, startTime) {
        switch (event.event) {
            case 'start':
                resultContent.innerHTML = '<div class="typing-indicator">Thinking...</div>';
                break;

            case 'chunk':
                // Remove typing indicator on first chunk
                const indicator = resultContent.querySelector('.typing-indicator');
                if (indicator) {
                    indicator.remove();
                }

                // Append content with markdown parsing
                const parsedContent = Utils.parseMarkdown(event.content);
                resultContent.innerHTML += parsedContent;

                // Scroll to bottom
                resultContent.scrollTop = resultContent.scrollHeight;
                break;

            case 'complete':
                // Update time
                const elapsed = Date.now() - startTime;
                document.getElementById('resultTime').textContent = `Time: ${(elapsed / 1000).toFixed(2)}s`;
                break;

            case 'error':
                this.showError(event.message);
                break;
        }
    },

    setupResultActions(answer, query, mode) {
        // Copy button
        const copyBtn = document.getElementById('copyResult');
        if (copyBtn) {
            copyBtn.onclick = async () => {
                const success = await Utils.copyToClipboard(answer);
                if (success) {
                    copyBtn.textContent = '✓ Copied';
                    setTimeout(() => {
                        copyBtn.textContent = '📋 Copy';
                    }, 2000);
                }
            };
        }

        // Export button
        const exportBtn = document.getElementById('exportResult');
        if (exportBtn) {
            exportBtn.onclick = () => {
                this.exportResult(answer, query, mode);
            };
        }
    },

    exportResult(answer, query, mode) {
        const timestamp = new Date().toISOString();
        const exportData = {
            query: query,
            mode: mode,
            answer: answer,
            timestamp: timestamp
        };

        // Create blob and download
        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `search-result-${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    },

    addToHistory(query, mode) {
        // Remove duplicates
        this.searchHistory = this.searchHistory.filter(item =>
            item.query !== query || item.mode !== mode
        );

        // Add to beginning
        this.searchHistory.unshift({
            query: query,
            mode: mode,
            timestamp: Date.now()
        });

        // Limit history size
        if (this.searchHistory.length > this.maxHistoryItems) {
            this.searchHistory = this.searchHistory.slice(0, this.maxHistoryItems);
        }

        // Save to localStorage
        this.saveHistory();

        // Re-render history
        this.renderHistory();
    },

    renderHistory() {
        const historyList = document.getElementById('historyList');
        if (!historyList) return;

        if (this.searchHistory.length === 0) {
            historyList.innerHTML = '<div class="history-empty">No recent searches</div>';
            return;
        }

        historyList.innerHTML = '';
        this.searchHistory.forEach(item => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';
            historyItem.innerHTML = `
                <span class="history-query">${Utils.escapeHtml(item.query)}</span>
                <span class="history-mode">${item.mode}</span>
            `;

            historyItem.addEventListener('click', () => {
                document.getElementById('searchQuery').value = item.query;
                document.getElementById('queryMode').value = item.mode;
                this.performSearch();
            });

            historyList.appendChild(historyItem);
        });
    },

    loadHistory() {
        const saved = Utils.storage.get('searchHistory');
        if (saved && Array.isArray(saved)) {
            this.searchHistory = saved;
        }
    },

    saveHistory() {
        Utils.storage.set('searchHistory', this.searchHistory);
    },

    clearHistory() {
        this.searchHistory = [];
        this.saveHistory();
        this.renderHistory();
    },

    showError(message) {
        const resultsDiv = document.getElementById('searchResults');
        resultsDiv.innerHTML = `
            <div class="search-error">
                <div class="error-icon">⚠️</div>
                <div class="error-message">${Utils.escapeHtml(message)}</div>
            </div>
        `;
    }
};

// Export for use
window.Search = Search;