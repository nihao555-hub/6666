import { createRouter, createWebHashHistory } from "vue-router";
import { store } from "./store";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/login", name: "login", component: () => import("./views/Login.vue") },
    {
      path: "/",
      component: () => import("./layouts/Console.vue"),
      children: [
        { path: "", redirect: "/overview" },
        { path: "overview", name: "overview", component: () => import("./views/Overview.vue") },
        { path: "shops", name: "shops", component: () => import("./views/Shops.vue") },
        { path: "habits", name: "habits", component: () => import("./views/ListingHabits.vue") },
        { path: "products", name: "products", component: () => import("./views/Products.vue") },
        { path: "feed", name: "feed", component: () => import("./views/Feed.vue") },
        { path: "templates", redirect: { name: "habits" } },
        { path: "drafts", name: "drafts", component: () => import("./views/Drafts.vue") },
        { path: "drafts/:id", name: "draft-detail", component: () => import("./views/DraftDetail.vue") },
        { path: "queue", name: "queue", component: () => import("./views/Queue.vue") },
        { path: "online", name: "online", component: () => import("./views/Online.vue") },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  if (to.path === "/login") return true;
  if (store.user) return true;
  try {
    await store.loadUser();
    return true;
  } catch {
    return { path: "/login" };
  }
});

export default router;
