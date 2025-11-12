<template>
  <div class="devicetree-container">
    <h2 class="devicetree-title">Devices & Sessions</h2>

    <div v-if="devices.length === 0" class="loading-state">
      <div class="loader"></div>
      <p>Loading devices...</p>
    </div>

    <ul class="device-list" v-else>
      <li v-for="device in devices" :key="device.id" class="device-item">
        <div
          class="device-header"
          @click="toggleDevices(device)"
          :class="{ expanded: device.expanded }"
        >
          <span class="expand-icon">{{ device.expanded ? "▼" : "▶" }}</span>
          <span class="device-id">{{ device.id }}</span>
        </div>

        <ul v-if="device.expanded" class="session-list">
          <li
            v-for="session in device.sessions || []"
            :key="session.id"
            class="session-item"
          >
            <div class="session-content">
              <span class="session-id">{{ session.id }}</span>
              <button
                @click="selectSession(device.id, session.id)"
                class="select-btn"
                :class="{ active: isSelected(device.id, session.id) }"
              >
                {{ isSelected(device.id, session.id) ? "✓ Active" : "View" }}
              </button>
            </div>
          </li>

          <li
            v-if="device.expanded && !device.sessions"
            class="loading-sessions"
          >
            <div class="mini-loader"></div>
            Loading sessions...
          </li>
        </ul>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { reactive, inject } from "vue";
import { collection, getDocs } from "firebase/firestore";
import { db } from "../utils/firebase.js";

const selectedSession = inject("selectedSession");

const devices = reactive([]);

// Load all devices initially
async function loadDevices() {
  const devicesSnapshot = await getDocs(collection(db, "devices"));
  devicesSnapshot.forEach((doc) => {
    devices.push({
      id: doc.id,
      expanded: false,
      sessions: null, // null means not loaded yet
    });
  });
}

loadDevices();

// Toggle devices dropdown and lazy-load sessions if not already loaded
async function toggleDevices(device) {
  device.expanded = !device.expanded;

  if (device.expanded && device.sessions === null) {
    const sessionsSnapshot = await getDocs(
      collection(db, "devices", device.id, "sessions")
    );
    device.sessions = sessionsSnapshot.docs.map((s) => ({
      id: s.id,
      ...s.data(),
    }));
  }
}

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

function isSelected(deviceId, sessionId) {
  return (
    selectedSession.deviceId === deviceId &&
    selectedSession.sessionId === sessionId
  );
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

.device-list {
  list-style: none;
  padding: 0;
}

.device-item {
  margin-bottom: 0.5rem;
}

.device-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  transition: all 0.3s ease;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.device-header:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.device-header.expanded {
  border-radius: 10px 10px 0 0;
}

.expand-icon {
  font-size: 0.75rem;
  transition: transform 0.3s ease;
  display: inline-block;
}

.device-header.expanded .expand-icon {
  transform: rotate(0deg);
}

.device-id {
  font-size: 0.95rem;
  flex: 1;
}

.session-list {
  list-style: none;
  padding: 0.5rem 0.5rem 0.5rem 1.5rem;
  background: #f8f9fa;
  border-radius: 0 0 10px 10px;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.05);
}

.session-item {
  margin-bottom: 0.5rem;
}

.session-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.75rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;
}

.session-content:hover {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  transform: translateX(4px);
}

.session-id {
  font-size: 0.9rem;
  color: #2c3e50;
  font-family: "Courier New", monospace;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.select-btn {
  padding: 0.5rem 1rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: all 0.3s ease;
  white-space: nowrap;
  box-shadow: 0 2px 4px rgba(102, 126, 234, 0.3);
}

.select-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(102, 126, 234, 0.4);
}

.select-btn:active {
  transform: translateY(0);
}

.select-btn.active {
  background: linear-gradient(135deg, #48c774 0%, #3ebd68 100%);
  box-shadow: 0 2px 4px rgba(72, 199, 116, 0.3);
}

.select-btn.active:hover {
  box-shadow: 0 4px 8px rgba(72, 199, 116, 0.4);
}

.loading-sessions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  color: #666;
  font-size: 0.9rem;
  font-style: italic;
}

.mini-loader {
  width: 16px;
  height: 16px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
</style>
