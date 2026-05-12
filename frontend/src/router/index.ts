import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const PublicLayout = () => import("@/components/layouts/PublicLayout.vue");
const AppLayout = () => import("@/components/layouts/AppLayout.vue");

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    component: PublicLayout,
    children: [
      {
        path: "",
        name: "login",
        component: () => import("@/pages/Login.vue"),
        meta: { guestOnly: true, title: "Accedi" },
      },
    ],
  },
  {
    path: "/register",
    component: PublicLayout,
    children: [
      {
        path: "",
        name: "register",
        component: () => import("@/pages/Register.vue"),
        meta: { guestOnly: true, title: "Registrati" },
      },
    ],
  },
  {
    path: "/forgot-password",
    component: PublicLayout,
    children: [
      {
        path: "",
        name: "forgot-password",
        component: () => import("@/pages/ForgotPassword.vue"),
        meta: { guestOnly: true, title: "Password dimenticata" },
      },
    ],
  },
  {
    path: "/reset-password",
    component: PublicLayout,
    children: [
      {
        path: "",
        name: "reset-password",
        component: () => import("@/pages/ResetPassword.vue"),
        meta: { guestOnly: true, title: "Reimposta password" },
      },
    ],
  },
  {
    path: "/verify-email-pending",
    component: PublicLayout,
    children: [
      {
        path: "",
        name: "verify-email-pending",
        component: () => import("@/pages/VerifyEmailPending.vue"),
        meta: { title: "Verifica email" },
      },
    ],
  },
  {
    path: "/verify-email",
    component: PublicLayout,
    children: [
      {
        path: "",
        name: "verify-email",
        component: () => import("@/pages/VerifyEmailToken.vue"),
        meta: { title: "Verifica email" },
      },
    ],
  },
  {
    path: "/me",
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: { name: "feed" },
      },
      {
        path: "feed",
        name: "feed",
        component: () => import("@/pages/Feed.vue"),
        meta: { title: "Il mio feed" },
      },
      {
        path: "feed/:categoryId(\\d+)",
        name: "feed-category",
        component: () => import("@/pages/Feed.vue"),
        meta: { title: "Il mio feed" },
      },
      {
        path: "categories",
        name: "categories",
        component: () => import("@/pages/Categories.vue"),
        meta: { title: "Categorie" },
      },
      {
        path: "sources",
        name: "sources",
        component: () => import("@/pages/Sources.vue"),
        meta: { title: "Fonti" },
      },
      {
        path: "sources/add",
        name: "sources-add",
        component: () => import("@/pages/AddSource.vue"),
        meta: { title: "Aggiungi fonte" },
      },
      {
        path: "article/:id",
        name: "article-detail",
        component: () => import("@/pages/ArticleDetail.vue"),
        meta: { title: "Articolo" },
        props: true,
      },
      {
        path: "search",
        name: "search",
        component: () => import("@/pages/Search.vue"),
        meta: { title: "Ricerca" },
      },
      {
        path: "notifications",
        name: "notifications",
        component: () => import("@/pages/Notifications.vue"),
        meta: { title: "Notifiche" },
      },
      {
        path: "alerts",
        name: "alerts",
        component: () => import("@/pages/Alerts.vue"),
        meta: { title: "Alert" },
      },
      {
        path: "saved",
        name: "saved",
        component: () => import("@/pages/Saved.vue"),
        meta: { title: "Salvati" },
      },
      {
        path: "settings",
        name: "settings",
        redirect: { name: "settings-account" },
      },
      {
        path: "settings/account",
        name: "settings-account",
        component: () => import("@/pages/AccountSettings.vue"),
        meta: { title: "Account" },
      },
      {
        path: "settings/privacy",
        name: "settings-privacy",
        component: () => import("@/pages/PrivacySettings.vue"),
        meta: { title: "Privacy" },
      },
      {
        path: "settings/aspect",
        name: "settings-aspect",
        component: () => import("@/pages/AspectSettings.vue"),
        meta: { title: "Aspetto" },
      },
      {
        path: "settings/notifications",
        name: "settings-notifications",
        component: () => import("@/pages/NotificationSettings.vue"),
        meta: { title: "Notifiche" },
      },
      {
        path: "settings/devices",
        name: "settings-devices",
        component: () => import("@/pages/Devices.vue"),
        meta: { title: "Dispositivi" },
      },
    ],
  },
  {
    path: "/:catchAll(.*)*",
    name: "not-found",
    component: () => import("@/pages/NotFound.vue"),
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.hydrated) await auth.hydrate();

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { next: to.fullPath } };
  }
  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: "feed" };
  }
  return true;
});

router.afterEach((to) => {
  const title = to.meta.title as string | undefined;
  document.title = title ? `${title} — YouFeed` : "YouFeed";
});
