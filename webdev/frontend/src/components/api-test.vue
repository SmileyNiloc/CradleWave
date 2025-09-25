<template>
  <div>
    <button @click="callApi">Call API</button>
    <div v-if="response">Response: {{ response }}</div>
  </div>
</template>

<script setup>
import { ref } from "vue";

const response = ref(null);

const callApi = async () => {
  try {
    const res = await fetch(`${process.env.VUE_APP_API_URL}/api/hello`);
    const data = await res.json();
    response.value = JSON.stringify(data);
  } catch (err) {
    response.value = "Error: " + err.message;
  }
};
</script>

<style scoped>
button {
  margin: 10px;
}
</style>
