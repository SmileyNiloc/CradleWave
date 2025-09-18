<template>
  <div>
    <button @click="callApi">Call API</button>
    <div v-if="response">Response: {{ response }}</div>
  </div>
</template>

<script>
export default {
  name: "ApiTest",
  data() {
    return {
      response: null,
    };
  },
  methods: {
    async callApi() {
      try {
        const res = await fetch("http://localhost:3047/api/hello");
        const text = await res.text();
        this.response = text;
      } catch (err) {
        this.response = "Error: " + err;
      }
    },
  },
};
</script>

<style scoped>
button {
  margin: 10px;
}
</style>
