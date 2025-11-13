import { createApp } from "vue";
import App from "./App.vue";
import { VueFire, VueFireFirestoreOptionsAPI } from "vuefire";
import { firebaseApp } from "./utils/firebase";

// Suppress ResizeObserver loop errors (common with chart libraries)
const resizeObserverErr = window.console.error;
window.console.error = (...args) => {
  if (
    args.length > 0 &&
    typeof args[0] === "string" &&
    args[0].includes("ResizeObserver")
  ) {
    return;
  }
  resizeObserverErr(...args);
};

// Also suppress in window error handler
window.addEventListener("error", (e) => {
  if (e.message && e.message.includes("ResizeObserver")) {
    e.stopImmediatePropagation();
    return false;
  }
});

const app = createApp(App);

// Setup VueFire
app.use(VueFire, {
  firebaseApp,
  modules: [VueFireFirestoreOptionsAPI()],
});

app.mount("#app");
