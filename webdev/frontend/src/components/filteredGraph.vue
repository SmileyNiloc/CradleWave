<template>
  <div v-if="selectedSession.deviceId != null" class="graph-container">
    <div class="graph-wrapper">
      <div class="toggle-controls">
        <button
          :class="['toggle-btn', { active: displayMode === 'Both' }]"
          @click="displayMode = 'Both'"
        >
          Both
        </button>
        <button
          :class="['toggle-btn', { active: displayMode === 'Heart' }]"
          @click="displayMode = 'Heart'"
        >
          Heart
        </button>
        <button
          :class="['toggle-btn', { active: displayMode === 'Breath' }]"
          @click="displayMode = 'Breath'"
        >
          Breathing
        </button>
      </div>
      <v-chart :option="chartOption" autoresize class="chart" />
      <div v-if="graphDataHR.length === 0" class="no-data-overlay">
        <p>No data available in this collection</p>
      </div>
    </div>
  </div>
  <div v-else class="empty-state">
    <div class="empty-icon">📊</div>
    <h3>No Device Selected</h3>
    <p>Select a device from the sidebar to view filtered wave data</p>
  </div>
</template>

<script setup>
import { computed, inject, watch, ref } from "vue";
import { useCollection } from "vuefire";
import {
  collection,
  query,
  orderBy,
  limit,
  documentId
} from "firebase/firestore";
import { db } from "../utils/firebase.js";
import VChart from "vue-echarts";

const selectedSession = inject("selectedSession");

const displayMode = ref("Both");

const recentDocsRef = ref(null);
const recentDocs = useCollection(recentDocsRef);

watch(
  () => selectedSession.deviceId,
  (newDeviceId) => {
    if (!newDeviceId) {
      recentDocsRef.value = null;
      return;
    }
    recentDocsRef.value = query(
      collection(db, "devices", newDeviceId, "filtered_data"),
      orderBy(documentId(), "desc"),
      limit(1)
    );
  },
  { immediate: true }
);

// We need two series for this graph: Filtered Heart and Filtered Breath
const graphDataHR = computed(() => {
  if (!recentDocs.value || recentDocs.value.length === 0) return [];
  const latestDoc = recentDocs.value[0];
  if (!latestDoc.data_points || latestDoc.data_points.length === 0) return [];

  // Plot just the latest 20 seconds of data from the last timepoint
  const lastDp = latestDoc.data_points[latestDoc.data_points.length - 1];
  if (
    !lastDp ||
    !lastDp.timestamp ||
    !lastDp.timestamp.toDate ||
    !Array.isArray(lastDp.filtered_heart)
  ) {
    return [];
  }

  const endTime = lastDp.timestamp.toDate().getTime();
  const startTime = endTime - 20 * 1000; // 20 seconds
  const numPoints = lastDp.filtered_heart.length;

  const points = [];
  for (let i = 0; i < numPoints; i++) {
    const time =
      startTime + (i / (numPoints > 1 ? numPoints - 1 : 1)) * 20 * 1000;
    points.push([time, lastDp.filtered_heart[i]]);
  }
  return points;
});

const graphDataBR = computed(() => {
  if (!recentDocs.value || recentDocs.value.length === 0) return [];
  const latestDoc = recentDocs.value[0];
  if (!latestDoc.data_points || latestDoc.data_points.length === 0) return [];

  const lastDp = latestDoc.data_points[latestDoc.data_points.length - 1];
  if (
    !lastDp ||
    !lastDp.timestamp ||
    !lastDp.timestamp.toDate ||
    !Array.isArray(lastDp.filtered_breath)
  ) {
    return [];
  }

  const endTime = lastDp.timestamp.toDate().getTime();
  const startTime = endTime - 20 * 1000; // 20 seconds
  const numPoints = lastDp.filtered_breath.length;

  const points = [];
  for (let i = 0; i < numPoints; i++) {
    const time =
      startTime + (i / (numPoints > 1 ? numPoints - 1 : 1)) * 20 * 1000;
    points.push([time, lastDp.filtered_breath[i]]);
  }
  return points;
});

const chartOption = computed(() => {
  const pointsHR = graphDataHR.value;
  const pointsBR = graphDataBR.value;

  let latestTime = Date.now();
  let minTime = latestTime - 20 * 1000;

  if (pointsHR.length > 0) {
    latestTime = pointsHR[pointsHR.length - 1][0];
    minTime = pointsHR[0][0];
  } else if (pointsBR.length > 0) {
    latestTime = pointsBR[pointsBR.length - 1][0];
    minTime = pointsBR[0][0];
  }

  return {
    title: {
      text: "Filtered Heart & Breath Signals",
      left: "center",
      textStyle: { color: "#333", fontSize: 18, fontWeight: "bold" }
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(50, 50, 50, 0.9)",
      borderColor: "#95a5a6",
      borderWidth: 1,
      textStyle: { color: "#fff" }
    },
    legend: {
      data: ["Filtered Heart", "Filtered Breath"],
      bottom: "5%",
      selected: {
        "Filtered Heart":
          displayMode.value === "Both" || displayMode.value === "Heart",
        "Filtered Breath":
          displayMode.value === "Both" || displayMode.value === "Breath"
      }
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "15%",
      top: "15%",
      containLabel: true
    },
    xAxis: {
      type: "time",
      min: minTime,
      max: latestTime,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#666" } },
      axisLabel: {
        color: "#666",
        fontSize: 11,
        rotate: 45,
        formatter: (value) => new Date(value).toLocaleTimeString()
      },
      splitLine: { show: true, lineStyle: { color: "#e0e0e0", type: "dashed" } }
    },
    yAxis: {
      type: "value",
      name: "Amplitude",
      nameTextStyle: { color: "#666", fontSize: 12, padding: [0, 0, 0, 10] },
      scale: true,
      min: (value) => Math.min(value.min, -0.1),
      max: (value) => Math.max(value.max, 0.1),
      axisLine: { lineStyle: { color: "#666" } },
      axisLabel: { color: "#666", fontSize: 11 },
      splitLine: { lineStyle: { color: "#e0e0e0", type: "dashed" } }
    },
    series: [
      {
        name: "Filtered Heart",
        type: "line",
        smooth: true,
        data: pointsHR,
        showSymbol: false,
        sampling: "lttb",
        lineStyle: { color: "#e74c3c", width: 2 }
      },
      {
        name: "Filtered Breath",
        type: "line",
        smooth: true,
        data: pointsBR,
        showSymbol: false,
        sampling: "lttb",
        lineStyle: { color: "#3498db", width: 2 }
      }
    ],
    dataZoom: [{ type: "slider", bottom: 0, height: 20 }, { type: "inside" }]
  };
});
</script>

<style scoped>
.toggle-controls {
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  z-index: 10;
  display: flex;
  gap: 0.5rem;
  background: #f8f9fa;
  padding: 0.25rem;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}
.toggle-btn {
  background: transparent;
  border: none;
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  color: #6c757d;
  cursor: pointer;
  transition: all 0.2s ease;
}
.toggle-btn:hover {
  background: #e9ecef;
  color: #495057;
}
.toggle-btn.active {
  background: white;
  color: #2c3e50;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}
.graph-container {
  width: 100%;
}
.graph-wrapper {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 1.5rem;
  height: 650px;
  position: relative;
  overflow: hidden;
}
.no-data-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  color: #666;
}
.empty-state {
  text-align: center;
  padding: 3rem;
  background: white;
  border-radius: 16px;
  color: #666;
}
.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}
</style>
