<template>
  <div>
    <h2>Users & Sessions</h2>
    <ul>
      <li v-for="user in users" :key="user.id">
        <div @click="toggleUser(user)">
          <span>{{ user.expanded ? "▼" : "▶" }}</span> {{ user.id }}
        </div>

        <ul v-if="user.expanded">
          <li v-for="session in user.sessions || []" :key="session.id">
            {{ session.id }}
            <button @click="selectSession(user.id, session.id)">
              Disply Session
            </button>
          </li>

          <li v-if="user.expanded && !user.sessions">Loading sessions...</li>
        </ul>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { reactive, inject } from "vue";
import { collection, getDocs } from "firebase/firestore";
import { db } from "../utils/firebase.js";

const selectedSession = inject("selectedSession");

const users = reactive([]);

// Load all users initially
async function loadUsers() {
  const usersSnapshot = await getDocs(collection(db, "users"));
  usersSnapshot.forEach((doc) => {
    users.push({
      id: doc.id,
      expanded: false,
      sessions: null, // null means not loaded yet
    });
  });
}

loadUsers();

// Toggle user dropdown and lazy-load sessions if not already loaded
async function toggleUser(user) {
  user.expanded = !user.expanded;

  if (user.expanded && user.sessions === null) {
    const sessionsSnapshot = await getDocs(
      collection(db, "users", user.id, "sessions")
    );
    user.sessions = sessionsSnapshot.docs.map((s) => ({
      id: s.id,
      ...s.data(),
    }));
  }
}

function selectSession(userId, sessionId) {
  selectedSession.userId = userId;
  selectedSession.sessionId = sessionId;
}
</script>

<style scoped>
ul {
  list-style: none;
  padding-left: 1em;
}
li {
  margin: 5px 0;
}
div {
  cursor: pointer;
  user-select: none;
}
</style>
