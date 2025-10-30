import { createApp } from "vue";
import App from "./App.vue";
import { VueFire, VueFireFirestoreOptionsAPI } from "vuefire";
import { firebaseApp } from "./utils/firebase";

const app = createApp(App);

// Setup VueFire
app.use(VueFire, {
  firebaseApp,
  modules: [VueFireFirestoreOptionsAPI()],
});

app.mount("#app");
