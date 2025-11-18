<template>
  <div v-if="selectedSession.sessionId != null" class="graph-container">
    <div class="graph-wrapper">
      <v-chart :option="chartOption" autoresize class="chart" />
      <div v-if="heartRateData.collection.length === 0" class="no-data-overlay">
        <p>No radar data available in this collection</p>
      </div>
    </div>
  </div>
  <div v-else class="empty-state">
    <div class="empty-icon">📡</div>
    <h3>No Session Selected</h3>
    <p>Select a device and session from the sidebar to view radar frame data</p>
  </div>
</template>

<script setup>
import { computed, inject, watch, reactive } from "vue";
import { useCollection } from "vuefire";
import { collection, query, orderBy } from "firebase/firestore";
import { db } from "../utils/firebase.js";
import VChart from "vue-echarts";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

// Register ECharts components globally
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
  CanvasRenderer,
]);

// Register component locally
const selectedSession = inject("selectedSession");

let heartRateData = reactive({
  collection: useCollection(),
});

// Watch Firestore for updates
watch(
  () => selectedSession,
  (newVal) => {
    console.log("Selected session changed:", newVal);
    if (!newVal || !newVal.sessionId) {
      console.log("Missing required fields for data fetch");
      return;
    }

    console.log(
      `Fetching data from: devices/${newVal.deviceId}/sessions/${newVal.sessionId}/frame_data`
    );
    const readingsRef = collection(
      db,
      "devices",
      newVal.deviceId,
      "sessions",
      newVal.sessionId,
      "frame_data"
    );
    const q = query(readingsRef, orderBy("frame_count"));
    heartRateData.collection = useCollection(q);
  },
  { deep: true, immediate: true }
);

// Limit to 250 most recent
watch(
  () => heartRateData.collection,
  (newVal) => {
    console.log(`Received ${newVal.length} data points from Firestore`);
    if (newVal.length > 0) {
      console.log("Sample data point:", newVal[0]);
    }
    if (newVal.length > 250) {
      heartRateData.collection.splice(0, newVal.length - 250);
    }
  }
);

// Computed ECharts option
const chartOption = computed(() => ({
  title: {
    text: "Real-Time Radar Frame Monitor",
    left: "center",
    textStyle: {
      color: "#333",
      fontSize: 18,
      fontWeight: "bold",
    },
  },
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(30, 30, 50, 0.95)",
    borderColor: "#3498db",
    borderWidth: 2,
    textStyle: {
      color: "#fff",
    },
    formatter: (params) => {
      if (!params || params.length === 0) return "";
      const point = params[0];
      return `
        <div style="padding: 5px;">
          <strong>Frame:</strong> ${point.axisValue}<br/>
          <strong style="color: #3498db;">Signal Strength:</strong> ${point.value} dB
        </div>
      `;
    },
  },
  grid: {
    left: "3%",
    right: "4%",
    bottom: "10%",
    top: "15%",
    containLabel: true,
  },
  xAxis: {
    type: "category",
    data: heartRateData.collection.map((d, index) => `Frame ${index + 1}`),
    boundaryGap: false,
    axisLine: {
      lineStyle: {
        color: "#3498db",
        width: 2,
      },
    },
    axisLabel: {
      color: "#555",
      fontSize: 11,
      rotate: 45,
    },
    splitLine: {
      show: true,
      lineStyle: {
        color: "#e8f4f8",
        type: "solid",
      },
    },
  },
  yAxis: {
    type: "value",
    name: "Signal (dB)",
    nameTextStyle: {
      color: "#555",
      fontSize: 12,
      padding: [0, 0, 0, 10],
      fontWeight: "bold",
    },
    scale: true,
    axisLine: {
      lineStyle: {
        color: "#3498db",
        width: 2,
      },
    },
    axisLabel: {
      color: "#555",
      fontSize: 11,
    },
    splitLine: {
      lineStyle: {
        color: "#e8f4f8",
        type: "solid",
      },
    },
  },
  series: [
    {
      name: "Radar Frame",
      type: "line",
      smooth: false,
      data: heartRateData.collection.map((d) => d.frame_db),
      showSymbol: true,
      symbolSize: 4,
      symbol: "circle",
      sampling: "lttb",
      lineStyle: {
        color: "#3498db",
        width: 2,
        shadowColor: "rgba(52, 152, 219, 0.5)",
        shadowBlur: 8,
      },
      itemStyle: {
        color: "#3498db",
        borderColor: "#2980b9",
        borderWidth: 2,
      },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {
            offset: 0,
            color: "rgba(52, 152, 219, 0.4)",
          },
          {
            offset: 1,
            color: "rgba(52, 152, 219, 0.05)",
          },
        ]),
      },
      emphasis: {
        focus: "series",
        lineStyle: {
          width: 3,
        },
        itemStyle: {
          borderWidth: 3,
          shadowBlur: 10,
          shadowColor: "rgba(52, 152, 219, 0.8)",
        },
      },
      animation: true,
      animationDuration: 200,
      animationEasing: "linear",
    },
  ],
  animationDuration: 200,
  animationEasing: "linear",
}));
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
