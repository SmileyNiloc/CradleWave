<template>
  <div class="devicetree-container">
    <h2 class="devicetree-title">Devices</h2>

    <div v-if="devices.length === 0" class="loading-state">
      <div class="loader"></div>
      <p>Loading devices...</p>
    </div>

    <div class="device-grid" v-else>
      <div
        v-for="device in devices"
        :key="device.id"
        class="device-card"
        :class="{ active: isDeviceActive(device.id) }"
      >
        <div class="card-main" @click="selectDeviceLatestSession(device)">
          <div class="device-icon">📶</div>
          <div class="device-info">
            <h3 class="device-name">{{ device.id }}</h3>
            <p class="device-status">
              {{
                device.sessions && device.sessions.length > 0
                  ? `${device.sessions.length} session${
                      device.sessions.length !== 1 ? "s" : ""
                    }`
                  : "No sessions"
              }}
            </p>
          </div>
          <div
            v-if="device.sessions && device.sessions.length > 0"
            class="latest-badge"
          >
            Latest
          </div>
        </div>

        <div class="card-actions">
          <button
            class="dropdown-btn"
            @click.stop="toggleSessions(device)"
            :class="{ expanded: device.expanded }"
            :disabled="!device.sessions || device.sessions.length === 0"
          >
            <span class="dropdown-icon">{{ device.expanded ? "▲" : "▼" }}</span>
            <span>Sessions</span>
          </button>
        </div>

        <div v-if="device.expanded" class="session-dropdown">
          <div
            v-for="session in device.sessions || []"
            :key="session.id"
            class="session-row"
            :class="{ selected: isSelected(device.id, session.id) }"
            @click="selectSession(device.id, session.id)"
          >
            <span class="session-label">{{ session.id }}</span>
            <span v-if="isSelected(device.id, session.id)" class="check-icon"
              >✓</span
            >
          </div>

          <div v-if="!device.sessions" class="loading-sessions">
            <div class="mini-loader"></div>
            Loading...
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, inject } from "vue";
import { collection, getDocs } from "firebase/firestore";
import { db } from "../utils/firebase.js";

const selectedSession = inject("selectedSession");

const devices = reactive([]);

// Load all devices initially and their sessions
async function loadDevices() {
  const devicesSnapshot = await getDocs(collection(db, "devices"));
  for (const doc of devicesSnapshot.docs) {
    const device = {
      id: doc.id,
      expanded: false,
      sessions: null,
    };

    // Load sessions immediately for each device
    await loadDeviceSessions(device);
    devices.push(device);
  }
}

// Load sessions for a specific device
async function loadDeviceSessions(device) {
  const sessionsSnapshot = await getDocs(
    collection(db, "devices", device.id, "sessions")
  );
  device.sessions = sessionsSnapshot.docs
    .map((s) => ({
      id: s.id,
      ...s.data(),
    }))
    .sort((a, b) => {
      // Sort by session ID in descending order (most recent first)
      // Session IDs are in format: session_YYYYMMDD_HHMMSS_xxxxx
      return b.id.localeCompare(a.id);
    });
}

loadDevices();

// Select the device's most recent session
async function selectDeviceLatestSession(device) {
  if (!device.sessions || device.sessions.length === 0) {
    return;
  }

  // Get the most recent session (first one in the list)
  const latestSession = device.sessions[0];
  selectSession(device.id, latestSession.id);
}

// Toggle sessions dropdown
function toggleSessions(device) {
  device.expanded = !device.expanded;
}

// Select a specific session
function selectSession(deviceId, sessionId) {
  // If clicking the same session again, deselect it
  if (
    selectedSession.deviceId === deviceId &&
    selectedSession.sessionId === sessionId
  ) {
    selectedSession.deviceId = null;
    selectedSession.sessionId = null;
  } else {
    // Otherwise, select the new session
    selectedSession.deviceId = deviceId;
    selectedSession.sessionId = sessionId;
  }
}

// Check if a specific session is selected
function isSelected(deviceId, sessionId) {
  return (
    selectedSession.deviceId === deviceId &&
    selectedSession.sessionId === sessionId
  );
}

// Check if any session from this device is active
function isDeviceActive(deviceId) {
  return selectedSession.deviceId === deviceId;
}
</script>

<style scoped>
.devicetree-container {
  width: 100%;
}

.devicetree-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 1.5rem;
  padding-bottom: 0.75rem;
  border-bottom: 2px solid #667eea;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  color: #666;
}

.loader {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.device-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.device-card {
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
  border: 2px solid transparent;
}

.device-card:hover {
  box-shadow: 0 4px 16px rgba(102, 126, 234, 0.2);
  transform: translateY(-2px);
}

.device-card.active {
  border-color: #48c774;
  box-shadow: 0 4px 16px rgba(72, 199, 116, 0.3);
}

.card-main {
  padding: 1.5rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 1rem;
  position: relative;
  transition: background 0.2s ease;
}

.card-main:hover {
  background: #f8f9fa;
}

.device-icon {
  font-size: 2.5rem;
  flex-shrink: 0;
}

.device-info {
  flex: 1;
  min-width: 0;
}

.device-name {
  font-size: 1.1rem;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 0.25rem 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-status {
  font-size: 0.85rem;
  color: #666;
  margin: 0;
}

.latest-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.card-actions {
  border-top: 1px solid #e0e0e0;
  padding: 0.5rem;
}

.dropdown-btn {
  width: 100%;
  padding: 0.75rem;
  background: transparent;
  border: none;
  color: #667eea;
  font-weight: 500;
  font-size: 0.9rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s ease;
  border-radius: 6px;
}

.dropdown-btn:not(:disabled):hover {
  background: #f0f2ff;
}

.dropdown-btn:disabled {
  color: #ccc;
  cursor: not-allowed;
}

.dropdown-btn.expanded {
  background: #f0f2ff;
}

.dropdown-icon {
  font-size: 0.7rem;
  transition: transform 0.3s ease;
}

.session-dropdown {
  border-top: 1px solid #e0e0e0;
  background: #f8f9fa;
  max-height: 200px;
  overflow-y: auto;
}

.session-row {
  padding: 0.875rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  transition: all 0.2s ease;
  border-bottom: 1px solid #e0e0e0;
}

.session-row:last-child {
  border-bottom: none;
}

.session-row:hover {
  background: white;
}

.session-row.selected {
  background: #e8f5e9;
  color: #48c774;
  font-weight: 500;
}

.session-label {
  font-size: 0.85rem;
  font-family: "Courier New", monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.check-icon {
  font-size: 1rem;
  color: #48c774;
  font-weight: bold;
}

.loading-sessions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1rem;
  color: #666;
  font-size: 0.85rem;
}

.mini-loader {
  width: 16px;
  height: 16px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Scrollbar styling for session dropdown */
.session-dropdown::-webkit-scrollbar {
  width: 6px;
}

.session-dropdown::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.session-dropdown::-webkit-scrollbar-thumb {
  background: #667eea;
  border-radius: 3px;
}

.session-dropdown::-webkit-scrollbar-thumb:hover {
  background: #764ba2;
}

@media (max-width: 768px) {
  .device-grid {
    grid-template-columns: 1fr;
  }
}
</style>
