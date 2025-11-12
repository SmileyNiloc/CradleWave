<template>
  <div>
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import {
  Chart as ChartJS,
  Title,
  Tooltip,
  Legend,
  LineElement,
  CategoryScale,
  LinearScale,
  PointElement,
  TimeScale,
} from "chart.js";
import { Line } from "vue-chartjs";
import { collection, query, orderBy } from "firebase/firestore";
import { useCollection } from "vuefire";
import { db } from "../utils/firebase.js";

ChartJS.register(
  Title,
  Tooltip,
  Legend,
  LineElement,
  CategoryScale,
  LinearScale,
  PointElement,
  TimeScale
);

const userId = "demo_user";
const sessionId = "session_20251111_170353_fa78cc";
const readingsRef = collection(
  db,
  "users",
  userId,
  "sessions",
  sessionId,
  "heart_rate_data"
);
const q = query(readingsRef, orderBy("time"));
const heartRateData = useCollection(q);

const chartData = computed(() => ({
  labels: heartRateData.value.map((d) =>
    new Date(d.time * 1000).toLocaleTimeString()
  ),
  datasets: [
    { label: "Heart Rate", data: heartRateData.value.map((d) => d.heart_rate) },
  ],
}));

const chartOptions = ref({ responseive: true });
</script>

<style scoped>
div {
  height: 400px;
}
</style>
