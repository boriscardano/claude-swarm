/**
 * Claude Swarm Dashboard
 * Real-time monitoring interface with SSE support
 */

class Dashboard {
    constructor() {
        this.apiBase = '/api/v1';
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        this.autoScroll = true;
        this.startTime = Date.now();

        // Track seen message IDs for efficient deduplication
        this.seenMessageIds = new Set();

        // DOM element references
        this.elements = {
            agentsContainer: document.getElementById('agentsContainer'),
            messagesContainer: document.getElementById('messagesContainer'),
            locksContainer: document.getElementById('locksContainer'),
            statsContainer: document.getElementById('statsContainer'),
            agentsCount: document.getElementById('agentsCount'),
            messagesCount: document.getElementById('messagesCount'),
            locksCount: document.getElementById('locksCount'),
            lastUpdated: document.getElementById('lastUpdated'),
            connectionStatus: document.getElementById('connectionStatus'),
            errorModal: document.getElementById('errorModal'),
            closeModal: document.getElementById('closeModal'),
            retryButton: document.getElementById('retryButton'),
            errorMessage: document.getElementById('errorMessage')
        };

        // Data cache
        this.cache = {
            agents: [],
            messages: [],
            locks: [],
            stats: {}
        };

        this.setupEventListeners();
    }

    setupEventListeners() {
        // Modal controls
        this.elements.closeModal.addEventListener('click', () => this.hideError());
        this.elements.retryButton.addEventListener('click', () => {
            this.hideError();
            this.reconnectAttempts = 0;
            this.init();
        });

        // Auto-scroll toggle on user scroll
        if (this.elements.messagesContainer) {
            this.elements.messagesContainer.addEventListener('scroll', () => {
                const container = this.elements.messagesContainer;
                const isScrolledToBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 50;
                this.autoScroll = isScrolledToBottom;
            });
        }
    }

    async init() {
        console.log('Initializing dashboard...');
        this.updateConnectionStatus('connecting');

        try {
            await this.loadInitialData();
            this.startEventStream();
            this.startTimestampUpdates();
            this.updateConnectionStatus('connected');
            this.reconnectAttempts = 0;
        } catch (error) {
            console.error('Initialization failed:', error);
            this.updateConnectionStatus('error');
            this.showError('Failed to load initial data. Please check if the backend is running.');
        }
    }

    async loadInitialData() {
        console.log('Loading initial data...');

        try {
            await Promise.all([
                this.loadAgents(),
                this.loadMessages(),
                this.loadLocks(),
                this.loadStats()
            ]);
        } catch (error) {
            console.error('Error loading initial data:', error);
            throw error;
        }
    }

    async fetchJSON(endpoint) {
        const response = await fetch(`${this.apiBase}${endpoint}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    }

    async loadAgents() {
        try {
            const data = await this.fetchJSON('/agents');
            this.cache.agents = data.agents || [];
            this.renderAgents();
        } catch (error) {
            console.error('Error loading agents:', error);
            this.renderAgentsError();
        }
    }

    async loadMessages() {
        try {
            const data = await this.fetchJSON('/messages');
            this.cache.messages = data.messages || [];
            this.renderMessages();
        } catch (error) {
            console.error('Error loading messages:', error);
            this.renderMessagesError();
        }
    }

    async loadLocks() {
        try {
            const data = await this.fetchJSON('/locks');
            this.cache.locks = data.locks || [];
            this.renderLocks();
        } catch (error) {
            console.error('Error loading locks:', error);
            this.renderLocksError();
        }
    }

    async loadStats() {
        try {
            const data = await this.fetchJSON('/stats');
            this.cache.stats = data;
            this.renderStats();
        } catch (error) {
            console.error('Error loading stats:', error);
            this.renderStatsError();
        }
    }

    startEventStream() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        console.log('Starting EventSource connection...');
        this.eventSource = new EventSource(`${this.apiBase}/stream`);

        this.eventSource.onopen = () => {
            console.log('EventSource connected');
            this.updateConnectionStatus('connected');
            this.reconnectAttempts = 0;
        };

        // Handle named events from backend
        this.eventSource.addEventListener('connected', (event) => {
            console.log('SSE connected:', JSON.parse(event.data));
        });

        this.eventSource.addEventListener('agents', (event) => {
            try {
                const data = JSON.parse(event.data);
                this.cache.agents = data.agents || [];
                this.renderAgents();
                this.updateLastUpdated();
            } catch (error) {
                console.error('Error parsing agents event:', error);
            }
        });

        this.eventSource.addEventListener('locks', (event) => {
            try {
                const data = JSON.parse(event.data);
                this.cache.locks = data.locks || [];
                this.renderLocks();
                this.updateLastUpdated();
            } catch (error) {
                console.error('Error parsing locks event:', error);
            }
        });

        this.eventSource.addEventListener('messages', (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.messages && data.messages.length > 0) {
                    // Add new messages to cache - addMessage now handles deduplication
                    data.messages.forEach(msg => {
                        this.addMessage(msg);
                    });
                }
                this.updateLastUpdated();
            } catch (error) {
                console.error('Error parsing messages event:', error);
            }
        });

        this.eventSource.addEventListener('stats', (event) => {
            try {
                const data = JSON.parse(event.data);
                this.cache.stats = {
                    active_agents: data.agent_count,
                    total_messages: data.message_count,
                    active_locks: data.lock_count,
                    uptime: null
                };
                this.renderStats();
                this.updateLastUpdated();
            } catch (error) {
                console.error('Error parsing stats event:', error);
            }
        });

        this.eventSource.addEventListener('heartbeat', (event) => {
            // Just log heartbeats, don't need to do anything
            // console.log('Heartbeat received');
        });

        this.eventSource.addEventListener('error', (event) => {
            console.error('Server error event:', JSON.parse(event.data));
        });

        // Generic message handler (for backwards compatibility)
        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleUpdate(data);
            } catch (error) {
                console.error('Error parsing SSE message:', error);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('EventSource error:', error);
            this.updateConnectionStatus('error');
            this.eventSource.close();

            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                console.log(`Reconnecting... (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                setTimeout(() => this.startEventStream(), this.reconnectDelay * this.reconnectAttempts);
            } else {
                this.showError('Lost connection to server. Maximum reconnection attempts reached.');
            }
        };
    }

    handleUpdate(data) {
        this.updateLastUpdated();

        switch (data.type) {
            case 'agents':
                if (data.agents) {
                    this.cache.agents = data.agents;
                    this.renderAgents();
                }
                break;

            case 'message':
                if (data.message) {
                    this.addMessage(data.message);
                }
                break;

            case 'messages':
                if (data.messages) {
                    this.cache.messages = data.messages;
                    this.renderMessages();
                }
                break;

            case 'locks':
                if (data.locks) {
                    this.cache.locks = data.locks;
                    this.renderLocks();
                }
                break;

            case 'stats':
                if (data.stats) {
                    this.cache.stats = data.stats;
                    this.renderStats();
                }
                break;

            default:
                console.warn('Unknown update type:', data.type);
        }
    }

    renderAgents() {
        const agents = this.cache.agents;
        this.elements.agentsCount.textContent = agents.length;

        if (agents.length === 0) {
            this.elements.agentsContainer.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🤖</div>
                    <p>No active agents</p>
                </div>
            `;
            return;
        }

        const html = `
            <div class="agent-list">
                ${agents.map(agent => this.renderAgent(agent)).join('')}
            </div>
        `;

        this.elements.agentsContainer.innerHTML = html;
    }

    renderAgent(agent) {
        const status = this.getAgentStatus(agent.last_heartbeat);
        const timeAgo = this.formatTimeAgo(agent.last_heartbeat);

        return `
            <div class="agent-item ${status}">
                <div class="agent-info">
                    <span class="agent-status-dot ${status}"></span>
                    <span class="agent-name">${this.escapeHtml(agent.agent_id)}</span>
                </div>
                <div class="agent-meta">
                    <span class="agent-timestamp">${timeAgo}</span>
                    <span class="agent-pid">PID: ${agent.pid || 'N/A'}</span>
                </div>
            </div>
        `;
    }

    getAgentStatus(lastHeartbeat) {
        const now = Date.now();
        const timestamp = new Date(lastHeartbeat).getTime();
        const age = (now - timestamp) / 1000; // seconds

        if (age < 30) return 'active';
        if (age < 120) return 'stale';
        return 'dead';
    }

    renderMessages() {
        const messages = this.cache.messages;
        this.elements.messagesCount.textContent = messages.length;

        if (messages.length === 0) {
            this.elements.messagesContainer.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">💬</div>
                    <p>No messages yet</p>
                </div>
            `;
            return;
        }

        const html = `
            <div class="message-list">
                ${messages.map(msg => this.renderMessage(msg)).join('')}
            </div>
        `;

        this.elements.messagesContainer.innerHTML = html;
        this.scrollMessagesToBottom();
    }

    renderMessage(message) {
        const timeAgo = this.formatTimeAgo(message.timestamp);

        return `
            <div class="message-item ${message.msg_type}" data-timestamp="${message.timestamp}">
                <div class="message-header">
                    <span class="message-agent">${this.escapeHtml(message.sender)}</span>
                    <span class="message-type ${message.msg_type}">${message.msg_type}</span>
                </div>
                <div class="message-content">${this.escapeHtml(message.content || message.message || '')}</div>
                <div class="message-timestamp">${timeAgo}</div>
            </div>
        `;
    }

    addMessage(message) {
        // Create unique message ID
        const messageId = `${message.timestamp}-${message.sender}-${message.msg_type}-${message.recipient || ''}`;

        // Skip if already seen (O(1) lookup)
        if (this.seenMessageIds.has(messageId)) {
            return;
        }

        this.seenMessageIds.add(messageId);

        // Limit Set size to prevent unbounded growth
        if (this.seenMessageIds.size > 1000) {
            // Remove oldest entries (convert to array, slice, convert back)
            const entries = Array.from(this.seenMessageIds);
            this.seenMessageIds = new Set(entries.slice(-500));
        }

        // Add to cache
        this.cache.messages.unshift(message);

        // Limit cache size
        if (this.cache.messages.length > 100) {
            this.cache.messages = this.cache.messages.slice(0, 100);
        }

        this.elements.messagesCount.textContent = this.cache.messages.length;

        // Add to DOM
        const messageList = this.elements.messagesContainer.querySelector('.message-list');
        if (messageList) {
            const messageHtml = this.renderMessage(message);
            messageList.insertAdjacentHTML('afterbegin', messageHtml);

            // Remove excess messages from DOM
            const messageItems = messageList.querySelectorAll('.message-item');
            if (messageItems.length > 100) {
                messageItems[messageItems.length - 1].remove();
            }

            if (this.autoScroll) {
                this.scrollMessagesToBottom();
            }
        } else {
            this.renderMessages();
        }
    }

    renderLocks() {
        const locks = this.cache.locks;
        this.elements.locksCount.textContent = locks.length;

        if (locks.length === 0) {
            this.elements.locksContainer.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🔒</div>
                    <p>No active locks</p>
                </div>
            `;
            return;
        }

        const html = `
            <div class="lock-list">
                ${locks.map(lock => this.renderLock(lock)).join('')}
            </div>
        `;

        this.elements.locksContainer.innerHTML = html;
    }

    renderLock(lock) {
        // Handle both formats: direct fields and nested fields
        const resource = lock.resource || lock.file_path || 'Unknown';
        const holder = lock.holder || lock.agent_id || 'Unknown';
        const acquiredAt = lock.acquired_at || lock.timestamp;
        const timeAgo = acquiredAt ? this.formatTimeAgo(acquiredAt) : 'Unknown';

        return `
            <div class="lock-item">
                <div class="lock-resource">${this.escapeHtml(resource)}</div>
                <div class="lock-holder">Held by: <strong>${this.escapeHtml(holder)}</strong></div>
                <div class="lock-timestamp">Acquired ${timeAgo}</div>
            </div>
        `;
    }

    renderStats() {
        const stats = this.cache.stats;

        const html = `
            <div class="stat-card agents">
                <div class="stat-value">${stats.active_agents || 0}</div>
                <div class="stat-label">Active Agents</div>
            </div>
            <div class="stat-card messages">
                <div class="stat-value">${stats.total_messages || 0}</div>
                <div class="stat-label">Messages</div>
            </div>
            <div class="stat-card locks">
                <div class="stat-value">${stats.active_locks || 0}</div>
                <div class="stat-label">Active Locks</div>
            </div>
            <div class="stat-card uptime">
                <div class="stat-value">${this.formatUptime(stats.uptime)}</div>
                <div class="stat-label">Uptime</div>
            </div>
        `;

        this.elements.statsContainer.innerHTML = html;
    }

    // Error rendering methods
    renderAgentsError() {
        this.elements.agentsContainer.innerHTML = '<div class="loading">Error loading agents</div>';
    }

    renderMessagesError() {
        this.elements.messagesContainer.innerHTML = '<div class="loading">Error loading messages</div>';
    }

    renderLocksError() {
        this.elements.locksContainer.innerHTML = '<div class="loading">Error loading locks</div>';
    }

    renderStatsError() {
        this.elements.statsContainer.innerHTML = '<div class="loading">Error loading stats</div>';
    }

    // UI helper methods
    updateConnectionStatus(status) {
        const statusDot = this.elements.connectionStatus.querySelector('.status-dot');
        const statusText = this.elements.connectionStatus.querySelector('.status-text');

        statusDot.className = 'status-dot';

        switch (status) {
            case 'connected':
                statusDot.classList.add('connected');
                statusText.textContent = 'Connected';
                break;
            case 'connecting':
                statusText.textContent = 'Connecting...';
                break;
            case 'error':
                statusDot.classList.add('error');
                statusText.textContent = 'Disconnected';
                break;
        }
    }

    updateLastUpdated() {
        const now = new Date();
        this.elements.lastUpdated.textContent = `Last updated: ${now.toLocaleTimeString()}`;
    }

    showError(message) {
        this.elements.errorMessage.textContent = message;
        this.elements.errorModal.classList.add('active');
    }

    hideError() {
        this.elements.errorModal.classList.remove('active');
    }

    scrollMessagesToBottom() {
        if (this.autoScroll && this.elements.messagesContainer) {
            this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
        }
    }

    startTimestampUpdates() {
        setInterval(() => {
            this.updateTimestampsInDOM();
        }, 10000); // Update every 10 seconds
    }

    updateTimestampsInDOM() {
        // Update message timestamps in-place instead of full re-render
        document.querySelectorAll('.message-timestamp').forEach((el, index) => {
            const messageItem = el.closest('.message-item');
            if (messageItem) {
                const timestamp = messageItem.dataset.timestamp;
                if (timestamp) {
                    el.textContent = this.formatTimeAgo(timestamp);
                }
            }
        });

        // Update agent timestamps in-place
        document.querySelectorAll('.agent-timestamp').forEach((el, index) => {
            if (this.cache.agents[index] && this.cache.agents[index].last_heartbeat) {
                el.textContent = this.formatTimeAgo(this.cache.agents[index].last_heartbeat);
            }
        });

        // Update lock timestamps in-place
        document.querySelectorAll('.lock-timestamp').forEach((el, index) => {
            const lock = this.cache.locks[index];
            if (lock) {
                const acquiredAt = lock.acquired_at || lock.timestamp;
                if (acquiredAt) {
                    el.textContent = 'Acquired ' + this.formatTimeAgo(acquiredAt);
                }
            }
        });
    }

    // Utility methods
    formatTimeAgo(timestamp) {
        const now = Date.now();
        const time = new Date(timestamp).getTime();
        const diff = (now - time) / 1000; // seconds

        if (diff < 5) return 'just now';
        if (diff < 60) return `${Math.floor(diff)}s ago`;
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return `${Math.floor(diff / 86400)}d ago`;
    }

    formatUptime(seconds) {
        if (!seconds && seconds !== 0) {
            const uptime = (Date.now() - this.startTime) / 1000;
            seconds = uptime;
        }

        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);

        if (days > 0) return `${days}d ${hours}h`;
        if (hours > 0) return `${hours}h ${minutes}m`;
        return `${minutes}m`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Cleanup
    destroy() {
        if (this.eventSource) {
            this.eventSource.close();
        }
    }
}

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing dashboard...');
    const dashboard = new Dashboard();
    dashboard.init();

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        dashboard.destroy();
    });
});
