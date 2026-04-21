<template>
  <div v-if="selectedSession.deviceId != null" class="graph-container">
    <div class="graph-wrapper">
      <v-chart :option="chartOption" autoresize class="chart" />
      <div v-if="graphData.length === 0" class="no-data-overlay">
        <p>No data available in this collection</p>
      </div>
    </div>
  </div>
  <div v-else class="empty-state">
    <div class="empty-icon">📊</div>
    <h3>No Device Selected</h3>
    <p>Select a device from the sidebar to view breathing rate data</p>
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
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
  DataZoomComponent
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer
]);

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

    // Fetch only the most recent document for this device (1 hour of data)
    recentDocsRef.value = query(
      collection(db, "devices", newDeviceId, "filtered_data"),
      orderBy(documentId(), "desc"),
      limit(1)
    );
  },
  { immediate: true }
);

const graphData = computed(() => {
  if (!recentDocs.value || recentDocs.value.length === 0) return [];

  const points = [];
  const latestDoc = recentDocs.value[0];

  if (latestDoc.data_points) {
    latestDoc.data_points.forEach((dp) => {
      if (dp.timestamp && dp.timestamp.toDate) {
        const time = dp.timestamp.toDate().getTime();
        points.push([time, dp.breathing_rate]);
      }
    });
  }

  points.sort((a, b) => a[0] - b[0]);
  return points;
});

const chartOption = computed(() => {
  const points = graphData.value;

  return {
    title: {
      text: "Real-Time Breathing Monitor",
      left: "center",
      textStyle: { color: "#333", fontSize: 18, fontWeight: "bold" }
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(50, 50, 50, 0.9)",
      borderColor: "#3498db",
      borderWidth: 1,
      textStyle: { color: "#fff" },
      formatter: (params) => {
        if (!params || params.length === 0) return "";
        const point = params[0];
        const timeStr = new Date(point.value[0]).toLocaleTimeString();
        const val =
          point.value[1] !== undefined && point.value[1] !== null
            ? Number(point.value[1]).toFixed(0)
            : "N/A";
        return `
          <div style="padding: 5px;">
            <strong>Time:</strong> ${timeStr}<br/>
            <strong style="color: #3498db;">Breathing Rate:</strong> ${val} BPM
          </div>
        `;
      }
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "10%",
      top: "15%",
      containLabel: true
    },
    xAxis: {
      type: "time",
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
      name: "BPM",
      nameTextStyle: { color: "#666", fontSize: 12, padding: [0, 0, 0, 10] },
      scale: true,
      axisLine: { lineStyle: { color: "#666" } },
      axisLabel: { color: "#666", fontSize: 11 },
      splitLine: { lineStyle: { color: "#e0e0e0", type: "dashed" } }
    },
    series: [
      {
        name: "Breathing Rate",
        type: "line",
        smooth: true,
        data: points,
        showSymbol: false,
        symbolSize: 6,
        symbol: "circle",
        sampling: "lttb",
        lineStyle: {
          color: "#3498db",
          width: 3,
          shadowColor: "rgba(52, 152, 219, 0.4)",
          shadowBlur: 10
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(52, 152, 219, 0.3)" },
            { offset: 1, color: "rgba(52, 152, 219, 0.05)" }
          ])
        },
        emphasis: { focus: "series", lineStyle: { width: 4 } },
        animation: false
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
  height: 500px;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.graph-wrapper:hover {
  box-shadow: 0 6px 30px rgba(0, 0, 0, 0.12);
}

.chart {
  height: 100%;
  width: 100%;
}

.no-data-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #999;
  font-size: 1rem;
  pointer-events: none;
}

.empty-state {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 4rem 2rem;
  text-align: center;
  color: #666;
}

.empty-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-state h3 {
  font-size: 1.5rem;
  color: #2c3e50;
  margin-bottom: 0.5rem;
  font-weight: 600;
}

.empty-state p {
  font-size: 1rem;
  color: #666;
  max-width: 400px;
  margin: 0 auto;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .graph-wrapper {
    height: 400px;
    padding: 1rem;
  }

  .empty-state {
    padding: 3rem 1.5rem;
  }

  .empty-icon {
    font-size: 3rem;
  }

  .empty-state h3 {
    font-size: 1.25rem;
  }

  .empty-state p {
    font-size: 0.9rem;
  }
}
</style>
