<template>
  <div class="status-monitor" :class="{ 'status-offline': !isReceivingData }">
    <div class="status-header">
      <h2>System Status</h2>
      <div class="status-indicator">
        <span class="dot" :class="{ blink: isReceivingData }"></span>
        {{ isReceivingData ? "Live" : "Offline" }}
      </div>
    </div>

    <div class="metrics-grid">
      <div class="metric-card hr">
        <div class="metric-icon">❤️</div>
        <div class="metric-info">
          <div class="metric-label">Heart Rate</div>
          <div class="metric-value">
            <span v-if="latestHR !== null">{{ latestHR }}</span>
            <span v-else>--</span>
            <span class="unit">BPM</span>
          </div>
          <div class="metric-message" :class="hrStatus.class">
            {{ hrStatus.message }}
          </div>
        </div>
      </div>

      <div class="metric-card br">
        <div class="metric-icon">🫁</div>
        <div class="metric-info">
          <div class="metric-label">Breathing Rate</div>
          <div class="metric-value">
            <span v-if="latestBR !== null">{{ latestBR }}</span>
            <span v-else>--</span>
            <span class="unit">RPM</span>
          </div>
          <div class="metric-message" :class="brStatus.class">
            {{ brStatus.message }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, watch, ref, onUnmounted } from "vue";
import { useCollection } from "vuefire";
import {
  collection,
  query,
  orderBy,
  limit,
  documentId
} from "firebase/firestore";
import { db } from "../utils/firebase.js";

const selectedSession = inject("selectedSession");

const recentDocsRef = ref(null);
const recentDocs = useCollection(recentDocsRef);

const currentTime = ref(Date.now());

const latestData = computed(() => {
  if (!recentDocs.value || recentDocs.value.length === 0) return null;
  const latestDoc = recentDocs.value[0];
  if (!latestDoc.data_points || latestDoc.data_points.length === 0) return null;
  return latestDoc.data_points[latestDoc.data_points.length - 1];
});

const latestHR = computed(() =>
  latestData.value && latestData.value.heart_rate != null
    ? Math.round(latestData.value.heart_rate)
    : null
);

const latestBR = computed(() =>
  latestData.value && latestData.value.breathing_rate != null
    ? Math.round(latestData.value.breathing_rate)
    : null
);

const lastUpdateTime = computed(() => {
  if (!latestData.value) return 0;
  if (latestData.value.timestamp && latestData.value.timestamp.toDate) {
    return latestData.value.timestamp.toDate().getTime();
  }
  return Date.now();
});

// Setup a timer to constantly check if we're receiving data
let timerInterval = null;
watch(
  () => selectedSession.deviceId,
  (newDeviceId) => {
    if (timerInterval) clearInterval(timerInterval);

    if (!newDeviceId) {
      recentDocsRef.value = null;
      return;
    }

    recentDocsRef.value = query(
      collection(db, "devices", newDeviceId, "filtered_data"),
      orderBy(documentId(), "desc"),
      limit(1)
    );

    timerInterval = setInterval(() => {
      currentTime.value = Date.now();
    }, 1000);
  },
  { immediate: true }
);

onUnmounted(() => {
  if (timerInterval) clearInterval(timerInterval);
});

const isReceivingData = computed(() => {
  if (lastUpdateTime.value === 0) return false;
  // Deem offline if 30 seconds pass without an update
  return currentTime.value - lastUpdateTime.value < 30000;
});

const hrStatus = computed(() => {
  if (!isReceivingData.value || latestHR.value === null) {
    return { message: "Waiting for data...", class: "neutral" };
  }
  if (latestHR.value < 40)
    return { message: "Low Heart Rate", class: "warning" };
  if (latestHR.value > 120)
    return { message: "High Heart Rate", class: "warning" };
  return { message: "Normal Range", class: "good" };
});

const brStatus = computed(() => {
  if (!isReceivingData.value || latestBR.value === null) {
    return { message: "Waiting for data...", class: "neutral" };
  }
  if (latestBR.value < 8) return { message: "Low Breathing", class: "warning" };
  if (latestBR.value > 25)
    return { message: "High Breathing", class: "warning" };
  return { message: "Normal Range", class: "good" };
});
</script>

<style scoped>
.status-monitor {
  background: white;
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  margin-bottom: 2rem;
  transition: all 0.3s ease;
}

.status-monitor.status-offline {
  border-left: 4px solid #ef4444;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.status-header h2 {
  font-size: 1.2rem;
  color: #1f2937;
  margin: 0;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: #6b7280;
  background: #f3f4f6;
  padding: 0.4rem 0.8rem;
  border-radius: 20px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #9ca3af;
}

.status-monitor:not(.status-offline) .dot {
  background: #10b981;
}

.blink {
  animation: blink 1.5s infinite;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
}

.metric-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border-radius: 12px;
  background: #f9fafb;
}

.metric-icon {
  font-size: 2.5rem;
  background: white;
  width: 70px;
  height: 70px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
}

.hr .metric-icon {
  color: #ef4444;
}

.br .metric-icon {
  color: #3b82f6;
}

.metric-info {
  display: flex;
  flex-direction: column;
}

.metric-label {
  font-size: 0.85rem;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.metric-value {
  font-size: 2rem;
  font-weight: 700;
  color: #111827;
  display: flex;
  align-items: baseline;
  gap: 0.25rem;
}

.unit {
  font-size: 1rem;
  font-weight: 600;
  color: #6b7280;
}

.metric-message {
  font-size: 0.85rem;
  font-weight: 500;
}

.metric-message.neutral {
  color: #6b7280;
}
.metric-message.good {
  color: #10b981;
}
.metric-message.warning {
  color: #f59e0b;
}
</style>
