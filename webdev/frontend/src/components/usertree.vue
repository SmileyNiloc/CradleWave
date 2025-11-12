<template>
  <div class="usertree-container">
    <h2 class="usertree-title">Users & Sessions</h2>

    <div v-if="users.length === 0" class="loading-state">
      <div class="loader"></div>
      <p>Loading users...</p>
    </div>

    <ul class="user-list" v-else>
      <li v-for="user in users" :key="user.id" class="user-item">
        <div
          class="user-header"
          @click="toggleUser(user)"
          :class="{ expanded: user.expanded }"
        >
          <span class="expand-icon">{{ user.expanded ? "▼" : "▶" }}</span>
          <span class="user-id">{{ user.id }}</span>
        </div>

        <ul v-if="user.expanded" class="session-list">
          <li
            v-for="session in user.sessions || []"
            :key="session.id"
            class="session-item"
          >
            <div class="session-content">
              <span class="session-id">{{ session.id }}</span>
              <button
                @click="selectSession(user.id, session.id)"
                class="select-btn"
                :class="{ active: isSelected(user.id, session.id) }"
              >
                {{ isSelected(user.id, session.id) ? "✓ Active" : "View" }}
              </button>
            </div>
          </li>

          <li v-if="user.expanded && !user.sessions" class="loading-sessions">
            <div class="mini-loader"></div>
            Loading sessions...
          </li>
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
  // If clicking the same session again, deselect it
  if (
    selectedSession.userId === userId &&
    selectedSession.sessionId === sessionId
  ) {
    selectedSession.userId = null;
    selectedSession.sessionId = null;
  } else {
    // Otherwise, select the new session
    selectedSession.userId = userId;
    selectedSession.sessionId = sessionId;
  }
}

function isSelected(userId, sessionId) {
  return (
    selectedSession.userId === userId && selectedSession.sessionId === sessionId
  );
}
</script>

<style scoped>
.usertree-container {
  width: 100%;
}

.usertree-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 1.5rem;
  padding-bottom: 0.75rem;
  border-bottom: 2px solid #667eea;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  color: #666;
}

.loader {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.user-list {
  list-style: none;
  padding: 0;
}

.user-item {
  margin-bottom: 0.5rem;
}

.user-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  transition: all 0.3s ease;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.user-header:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.user-header.expanded {
  border-radius: 10px 10px 0 0;
}

.expand-icon {
  font-size: 0.75rem;
  transition: transform 0.3s ease;
  display: inline-block;
}

.user-header.expanded .expand-icon {
  transform: rotate(0deg);
}

.user-id {
  font-size: 0.95rem;
  flex: 1;
}

.session-list {
  list-style: none;
  padding: 0.5rem 0.5rem 0.5rem 1.5rem;
  background: #f8f9fa;
  border-radius: 0 0 10px 10px;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.05);
}

.session-item {
  margin-bottom: 0.5rem;
}

.session-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.75rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;
}

.session-content:hover {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  transform: translateX(4px);
}

.session-id {
  font-size: 0.9rem;
  color: #2c3e50;
  font-family: "Courier New", monospace;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.select-btn {
  padding: 0.5rem 1rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: all 0.3s ease;
  white-space: nowrap;
  box-shadow: 0 2px 4px rgba(102, 126, 234, 0.3);
}

.select-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(102, 126, 234, 0.4);
}

.select-btn:active {
  transform: translateY(0);
}

.select-btn.active {
  background: linear-gradient(135deg, #48c774 0%, #3ebd68 100%);
  box-shadow: 0 2px 4px rgba(72, 199, 116, 0.3);
}

.select-btn.active:hover {
  box-shadow: 0 4px 8px rgba(72, 199, 116, 0.4);
}

.loading-sessions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  color: #666;
  font-size: 0.9rem;
  font-style: italic;
}

.mini-loader {
  width: 16px;
  height: 16px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
</style>
