<template>
  <div v-if="selectedSession.sessionId != null" class="graph-container">
    <div class="graph-wrapper">
      <v-chart :option="chartOption" autoresize class="chart" />
      <div v-if="heartRateData.collection.length === 0" class="no-data-overlay">
        <p>No data available in this collection</p>
      </div>
    </div>
  </div>
  <div v-else class="empty-state">
    <div class="empty-icon">📊</div>
    <h3>No Session Selected</h3>
    <p>Select a device and session from the sidebar to view heart rate data</p>
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
      `Fetching data from: devices/${newVal.deviceId}/sessions/${newVal.sessionId}/heart_rate_data`
    );
    const readingsRef = collection(
      db,
      "devices",
      newVal.deviceId,
      "sessions",
      newVal.sessionId,
      "heart_rate_data"
    );
    const q = query(readingsRef, orderBy("time"));
    heartRateData.collection = useCollection(q);
  },
  { deep: true, immediate: true }
);

// Limit to 250 most recent
// watch(
//   () => heartRateData.collection,
//   (newVal) => {
//     console.log(`Received ${newVal.length} data points from Firestore`);
//     if (newVal.length > 0) {
//       console.log("Sample data point:", newVal[0]);
//     }
//     if (newVal.length > 250) {
//       heartRateData.collection.splice(0, newVal.length - 250);
//     }
//   }
// );

// Computed ECharts option
const chartOption = computed(() => ({
  title: {
    text: "Real-Time Heart Rate Monitor",
    left: "center",
    textStyle: {
      color: "#333",
      fontSize: 18,
      fontWeight: "bold",
    },
  },
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(50, 50, 50, 0.9)",
    borderColor: "#e74c3c",
    borderWidth: 1,
    textStyle: {
      color: "#fff",
    },
    formatter: (params) => {
      if (!params || params.length === 0) return "";
      const point = params[0];
      return `
        <div style="padding: 5px;">
          <strong>Frame:</strong> ${point.axisValue}<br/>
          <strong style="color: #e74c3c;">Heart Rate:</strong> ${point.value} BPM
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
    data: heartRateData.collection.map((d) =>
      Number(d.relative_time).toFixed(2)
    ),
    boundaryGap: false,
    min: (v) => v.max - 10,
    max: "dataMax",
    axisLine: {
      lineStyle: {
        color: "#666",
      },
    },
    axisLabel: {
      color: "#666",
      fontSize: 11,
      rotate: 45,
    },
    splitLine: {
      show: true,
      lineStyle: {
        color: "#e0e0e0",
        type: "dashed",
      },
    },
  },
  yAxis: {
    type: "value",
    name: "BPM",
    nameTextStyle: {
      color: "#666",
      fontSize: 12,
      padding: [0, 0, 0, 10],
    },
    scale: true,
    axisLine: {
      lineStyle: {
        color: "#666",
      },
    },
    axisLabel: {
      color: "#666",
      fontSize: 11,
    },
    splitLine: {
      lineStyle: {
        color: "#e0e0e0",
        type: "dashed",
      },
    },
  },
  series: [
    {
      name: "Heart Rate",
      type: "line",
      smooth: true,
      data: heartRateData.collection.map((d) => d.heart_rate),
      showSymbol: false,
      symbolSize: 6,
      symbol: "circle",
      sampling: "lttb",
      lineStyle: {
        color: "#e74c3c",
        width: 3,
        shadowColor: "rgba(231, 76, 60, 0.4)",
        shadowBlur: 10,
      },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {
            offset: 0,
            color: "rgba(231, 76, 60, 0.3)",
          },
          {
            offset: 1,
            color: "rgba(231, 76, 60, 0.05)",
          },
        ]),
      },
      emphasis: {
        focus: "series",
        lineStyle: {
          width: 4,
        },
      },
      animation: true,
      animationDuration: 300,
      animationEasing: "linear",
    },
  ],
  dataZoom: [
    {
      type: "slider",
      bottom: 0,
      height: 20,
    },
    {
      type: "inside",
    },
  ],
  animationDuration: 300,
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
