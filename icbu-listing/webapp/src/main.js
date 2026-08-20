import { createApp } from "vue";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/dist/index.css";

import App from "./App.vue";
import router from "./router";
import { attachApiAuth } from "./api";
import { store } from "./store";
import "./styles.css";

attachApiAuth({ router, store });

createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount("#app");
