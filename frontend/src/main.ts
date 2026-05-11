import { createApp } from "vue";
import { createPinia } from "pinia";
import { router } from "@/router";
import { useAuthStore } from "@/stores/auth";
import App from "@/App.vue";
import "@/style.css";

async function bootstrap() {
  const app = createApp(App);
  const pinia = createPinia();
  app.use(pinia);

  // Hydrate session BEFORE mounting router so navigation guards
  // see the correct auth state. Best-effort: failures = anonymous user.
  const auth = useAuthStore();
  await auth.hydrate();

  app.use(router);
  app.mount("#app");
}

bootstrap().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("[yf] bootstrap failed", err);
});
