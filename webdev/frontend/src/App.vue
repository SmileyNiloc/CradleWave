<script setup>
// import ApiTest from "./components/api-test.vue";
import devicetree from "./components/devicetree.vue";
import hrGraph from "./components/hrGraph.vue";
import { reactive, provide } from "vue";

const selection = reactive({
  deviceId: null,
  sessionId: null,
});
provide("selectedSession", selection);
</script>
<template>
  <div class="app-container">
    <header class="app-header">
      <div class="header-content">
        <h1 class="app-title">
          <span class="icon">❤️</span>
          CradleWave
        </h1>
        <p class="app-subtitle">Real-Time Heart Rate Monitoring System</p>
      </div>
    </header>

    <main class="main-content">
      <div class="content-grid">
        <aside class="sidebar">
          <devicetree />
        </aside>

        <section class="graph-section">
          <hrGraph />
          <div v-if="selection.sessionId" class="session-info">
            <div class="info-card">
              <span class="info-label">Device ID:</span>
              <span class="info-value">{{ selection.deviceId }}</span>
            </div>
            <div class="info-card">
              <span class="info-label">Session ID:</span>
              <span class="info-value">{{ selection.sessionId }}</span>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen,
    Ubuntu, Cantarell, "Helvetica Neue", sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #2c3e50;
  min-height: 100vh;
}

.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 2rem 2rem 3rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  position: relative;
  overflow: hidden;
}

.app-header::before {
  content: "";
  position: absolute;
  top: -50%;
  right: -10%;
  width: 300px;
  height: 300px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  animation: pulse 8s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.3;
  }
  50% {
    transform: scale(1.2);
    opacity: 0.1;
  }
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
  position: relative;
  z-index: 1;
}

.app-title {
  font-size: 2.5rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.icon {
  font-size: 2rem;
  animation: heartbeat 1.5s ease-in-out infinite;
}

@keyframes heartbeat {
  0%,
  100% {
    transform: scale(1);
  }
  10%,
  30% {
    transform: scale(1.1);
  }
  20%,
  40% {
    transform: scale(1);
  }
}

.app-subtitle {
  font-size: 1.1rem;
  opacity: 0.9;
  font-weight: 300;
}

.main-content {
  flex: 1;
  padding: 2rem;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

.content-grid {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 2rem;
  align-items: start;
}

.sidebar {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 1.5rem;
  position: sticky;
  top: 2rem;
  max-height: calc(100vh - 4rem);
  overflow-y: auto;
}

.graph-section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.session-info {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.info-card {
  background: white;
  border-radius: 12px;
  padding: 1rem 1.5rem;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
  min-width: 200px;
}

.info-label {
  font-size: 0.85rem;
  color: #666;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.info-value {
  font-size: 1.1rem;
  color: #2c3e50;
  font-weight: 600;
  word-break: break-all;
}

/* Scrollbar styling */
.sidebar::-webkit-scrollbar {
  width: 8px;
}

.sidebar::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 10px;
}

.sidebar::-webkit-scrollbar-thumb {
  background: #667eea;
  border-radius: 10px;
}

.sidebar::-webkit-scrollbar-thumb:hover {
  background: #764ba2;
}

/* Responsive design */
@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: relative;
    top: 0;
    max-height: 400px;
  }

  .app-title {
    font-size: 2rem;
  }
}

@media (max-width: 768px) {
  .main-content {
    padding: 1rem;
  }

  .app-header {
    padding: 1.5rem 1rem 2rem;
  }

  .app-title {
    font-size: 1.75rem;
  }

  .app-subtitle {
    font-size: 1rem;
  }
}
</style>
