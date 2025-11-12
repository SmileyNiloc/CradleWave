<script setup>
// import ApiTest from "./components/api-test.vue";
import usertree from "./components/usertree.vue";
import hrGraph from "./components/hrGraph.vue";
import { reactive, provide } from "vue";

const selection = reactive({
  userId: null,
  sessionId: null,
});
provide("selectedSession", selection);
</script>
<template>
  <title>CradleWave</title>
  <!-- <ApiTest /> -->
  <usertree />
  <hrGraph />
  <p>{{ selection }}</p>
</template>
<style>
#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}
</style>
