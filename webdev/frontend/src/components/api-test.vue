<template>
  <div>
    <button @click="callApi">Call API</button>
    <div v-if="response">Response: {{ response }}</div>
  </div>
</template>

<script setup>
import { ref } from "vue";

const response = ref(null);

async function callApi() {
  try {
    console.log(process.env.VUE_APP_TEST_VAR); // ✅ works
    console.log("API URL:");
    console.log(process.env.VUE_APP_API_URL); // ✅ works
    const res = await fetch(`${process.env.VUE_APP_API_URL}api/hello`);
    const text = await res.text();
    response.value = text;
  } catch (err) {
    response.value = "Error: " + err;
  }
}
</script>

<style scoped>
button {
  margin: 10px;
}
</style>
