<script setup>
import { useCollection } from "vuefire";
import { collection } from "firebase/firestore";
import { db } from "../utils/firebase.js";

// Use VueFire's useCollection composable for real-time updates
const items = useCollection(collection(db, "test_collection"));
</script>
<template>
  <div>
    <h2>Firestore Component (VueFire)</h2>
    <ul>
      <li v-for="item in items" :key="item.id">
        <strong>ID:</strong> {{ item.id }}
        <br />
        <strong>Data:</strong> {{ item }}
      </li>
    </ul>
  </div>
</template>
<style scoped>
h2 {
  color: #42b983;
}
ul {
  list-style-type: none;
  padding: 0;
}
li {
  background: #f9f9f9;
  margin: 5px 0;
  padding: 10px;
  border-radius: 4px;
}
</style>
