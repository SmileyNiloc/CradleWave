<template>
  <div v-if="selectedSession.deviceId != null" class="graph-container">
    <div class="graph-wrapper">
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
  const points = [];
  const latestDoc = recentDocs.value[0];
  if (latestDoc.data_points) {
    latestDoc.data_points.forEach((dp) => {
      if (dp.timestamp && dp.timestamp.toDate && dp.filtered_heart != null) {
        points.push([dp.timestamp.toDate().getTime(), dp.filtered_heart]);
      }
    });
  }
  points.sort((a, b) => a[0] - b[0]);
  if (points.length > 0) {
    const latestTime = points[points.length - 1][0];
    const fiveMinsAgo = latestTime - 5 * 60 * 1000;
    return points.filter((p) => p[0] >= fiveMinsAgo);
  }
  return points;
});

const graphDataBR = computed(() => {
  if (!recentDocs.value || recentDocs.value.length === 0) return [];
  const points = [];
  const latestDoc = recentDocs.value[0];
  if (latestDoc.data_points) {
    latestDoc.data_points.forEach((dp) => {
      if (dp.timestamp && dp.timestamp.toDate && dp.filtered_breath != null) {
        points.push([dp.timestamp.toDate().getTime(), dp.filtered_breath]);
      }
    });
  }
  points.sort((a, b) => a[0] - b[0]);
  if (points.length > 0) {
    const latestTime = points[points.length - 1][0];
    const fiveMinsAgo = latestTime - 5 * 60 * 1000;
    return points.filter((p) => p[0] >= fiveMinsAgo);
  }
  return points;
});

const chartOption = computed(() => {
  const pointsHR = graphDataHR.value;
  const pointsBR = graphDataBR.value;

  // Force a common X-axis range across all graphs based on the latest received point
  let latestTime = Date.now();
  if (pointsHR.length > 0) {
    latestTime = pointsHR[pointsHR.length - 1][0];
  }
  const minTime = latestTime - 5 * 60 * 1000;

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
      bottom: "5%"
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
