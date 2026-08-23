import { reactive } from "vue";
import { api } from "./api";

const SHOP_KEY = "auto-shoper.shop";
const SIDEBAR_KEY = "auto-shoper.sidebar-collapsed";

let ensureShopsPromise = null;

export const store = reactive({
  user: null,
  shops: [],
  shopId: localStorage.getItem(SHOP_KEY) || "",
  sidebarCollapsed: localStorage.getItem(SIDEBAR_KEY) === "1",

  get shop() {
    return this.shops.find((item) => item.id === this.shopId) || null;
  },

  async loadUser() {
    try {
      this.user = await api.me();
      return this.user;
    } catch (error) {
      this.reset();
      throw error;
    }
  },

  async loadShops() {
    try {
      this.shops = await api.shops();
    } catch (error) {
      if (String(error.message || "").includes("登录")) {
        this.reset();
      }
      throw error;
    }
    if (!this.shops.some((item) => item.id === this.shopId)) {
      this.selectShop(this.shops[0]?.id || "");
    }
    return this.shops;
  },

  async ensureShops() {
    if (ensureShopsPromise) return ensureShopsPromise;
    ensureShopsPromise = this._ensureShopsImpl().finally(() => {
      ensureShopsPromise = null;
    });
    return ensureShopsPromise;
  },

  async _ensureShopsImpl() {
    await this.loadShops();
    if (!this.shops.length) {
      try {
        const options = await api.shopConnectOptions();
        if (options.prefer_env_token) {
          await api.bindEnvShop("测试店铺");
          await this.loadShops();
        }
      } catch {
        /* bind-env unavailable in production without token */
      }
    }
    return this.shops;
  },

  selectShop(shopId) {
    this.shopId = shopId || "";
    if (this.shopId) {
      localStorage.setItem(SHOP_KEY, this.shopId);
    } else {
      localStorage.removeItem(SHOP_KEY);
    }
  },

  toggleSidebar() {
    this.sidebarCollapsed = !this.sidebarCollapsed;
    localStorage.setItem(SIDEBAR_KEY, this.sidebarCollapsed ? "1" : "0");
  },

  reset() {
    this.user = null;
    this.shops = [];
    this.selectShop("");
  },
});
