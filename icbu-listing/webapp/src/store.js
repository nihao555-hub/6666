import { reactive } from "vue";
import { api } from "./api";

const SHOP_KEY = "auto-shoper.shop";

export const store = reactive({
  user: null,
  shops: [],
  shopId: localStorage.getItem(SHOP_KEY) || "",

  get shop() {
    return this.shops.find((item) => item.id === this.shopId) || null;
  },

  async loadUser() {
    this.user = await api.me();
    return this.user;
  },

  async loadShops() {
    this.shops = await api.shops();
    if (!this.shops.some((item) => item.id === this.shopId)) {
      this.selectShop(this.shops[0]?.id || "");
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

  reset() {
    this.user = null;
    this.shops = [];
    this.selectShop("");
  },
});
