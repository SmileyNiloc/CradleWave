<script setup>
import ApiTest from "./components/api-test.vue";
import firestore from "./components/firestore.vue";
import hrGraph from "./components/hrGraph.vue";
</script>
<template>
  <title>CradleWave</title>
  <ApiTest />
  <firestore />
  <hrGraph />
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
