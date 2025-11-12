<template>
  <div v-if="selectedSession.sessionId != null">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup>
import { computed, ref, inject, watch, reactive } from "vue";
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

let heartRateData = reactive({
  collection: useCollection(),
});

const selectedSession = inject("selectedSession");
watch(
  () => selectedSession,
  (newVal) => {
    const readingsRef = collection(
      db,
      "users",
      newVal.userId,
      "sessions",
      newVal.sessionId,
      "heart_rate_data"
    );
    const q = query(readingsRef, orderBy("time"));
    heartRateData.collection = useCollection(q);
    console.log("Heart Rate Data Updated:", heartRateData.value);
  },
  { deep: true }
);

const chartData = computed(() => ({
  labels: heartRateData.collection.map((d) =>
    new Date(d.time * 1000).toLocaleTimeString()
  ),
  datasets: [
    {
      label: "Heart Rate",
      data: heartRateData.collection.map((d) => d.heart_rate),
    },
  ],
}));

watch(
  () => heartRateData.collection,
  (newVal) => {
    if (newVal.length > 10) {
      heartRateData.collection.splice(0, newVal.length - 50);
    }
  }
);

const chartOptions = ref({ responsive: true });
</script>

<style scoped>
div {
  height: 400px;
}
</style>
