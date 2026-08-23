import axios from "axios";

const http = axios.create({ baseURL: "/api/v1", withCredentials: true });

let authRouter = null;
let authStore = null;

export function attachApiAuth({ router, store }) {
  authRouter = router;
  authStore = store;
}

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status || 0;
    const detail = error.response?.data?.detail;
    const message = typeof detail === "string" ? detail : error.message || "请求失败";
    if (status === 401 && authStore) {
      authStore.reset();
      if (authRouter && authRouter.currentRoute.value.path !== "/login") {
        authRouter.push("/login");
      }
    }
    const wrapped = new Error(message);
    wrapped.status = status;
    return Promise.reject(wrapped);
  },
);

export const api = {
  me: () => http.get("/auth/me"),
  login: (payload) => http.post("/auth/login", payload),
  register: (payload) => http.post("/auth/register", payload),
  logout: () => http.post("/auth/logout"),

  overview: () => http.get("/overview"),
  health: () => http.get("/health"),

  shops: () => http.get("/shops"),
  shopConnectOptions: () => http.get("/shops/connect-options"),
  oauthStart: (embedded = false) => http.get("/alibaba/oauth/start", { params: { embedded } }),
  bindEnvShop: (name) => http.post("/shops/bind-env", { name }),
  unbindShop: (shopId) => http.delete(`/shops/${shopId}`),
  saveDefaults: (shopId, body) => http.post(`/shops/${shopId}/defaults`, body),
  shopDefaultOptions: (shopId, categoryId, extra = {}) =>
    http.get(`/shops/${shopId}/default-options`, {
      params: {
        category_id: categoryId || "",
        ...(extra.refresh ? { refresh: true } : {}),
        ...(extra.pull === false ? { pull: false } : {}),
      },
    }),
  onlineProducts: (shopId, params) => http.get(`/shops/${shopId}/online`, { params }),
  categories: (shopId, parent, extra = {}) =>
    http.get(`/shops/${shopId}/categories`, {
      params: {
        shop_id: shopId,
        parent,
        ...(extra.sidebar ? { sidebar: true } : {}),
      },
    }),
  categorySidebar: (shopId, extra = {}) =>
    http.get(`/shops/${shopId}/categories/sidebar`, {
      params: {
        shop_id: shopId,
        ...(extra.refresh ? { refresh: true } : {}),
      },
    }),
  recordCategoryPick: (shopId, body) => http.post(`/shops/${shopId}/categories/recent`, body),
  categorySchema: (shopId, categoryId) =>
    http.get(`/shops/${shopId}/categories/${categoryId}/schema`, { params: { shop_id: shopId } }),

  products: (params) => http.get("/products", { params }),
  product: (id) => http.get(`/products/${id}`),
  createProduct: (form) => http.post("/products", form),
  deleteProduct: (id) => http.delete(`/products/${id}`),
  distribute: (body) => http.post("/products/distribute", body),

  templates: (params) => http.get("/templates", { params }),
  createTemplate: (body) => http.post("/templates", body),
  updateTemplate: (id, body) => http.patch(`/templates/${id}`, body),
  deleteTemplate: (id) => http.delete(`/templates/${id}`),
  applyTemplate: (id, draftIds) => http.post(`/templates/${id}/apply`, { draft_ids: draftIds }),

  imageTemplates: () => http.get("/image-templates"),
  planImages: (body) => http.post("/image-templates/plan", body),
  generateImages: (body) => http.post("/image-templates/generate", body),
  uploadReference: (form) => http.post("/image-templates/reference", form),
  imageJob: (id) => http.get(`/image-templates/jobs/${id}`),
  feedFromGenerated: (body) => http.post("/listings/feed-from-generated", body),

  feed: (form) => http.post("/listings/feed", form),
  feedBatch: (form) => http.post("/listings/batch", form),
  batchProgress: (batchId, params) => http.get(`/batches/${batchId}`, { params }),
  feedSessions: (shopId) => http.get("/feed-sessions", { params: { shop_id: shopId || "" } }),
  getFeedSession: (id) => http.get(`/feed-sessions/${id}`),
  createFeedSession: (body) => http.post("/feed-sessions", body),
  saveFeedSession: (id, body) => http.patch(`/feed-sessions/${id}`, body),
  uploadFeedSessionFiles: (id, form) => http.post(`/feed-sessions/${id}/files`, form),
  dropFeedSession: (id) => http.delete(`/feed-sessions/${id}`),

  excelStyles: () => http.get("/excel/styles"),
  excelSheetPlan: (params) => http.get("/excel/sheet-plan", { params }),
  excelSmartPlan: (params) => http.get("/excel/smart-plan", { params }),
  excelSmartPlanFromImages: (form) => http.post("/excel/smart-plan-from-images", form),
  excelEcosystemBrief: (params) => http.get("/excel/ecosystem-brief", { params }),
  excelSmartTemplateFromPlan: (body) =>
    http.post("/excel/smart-template-from-plan", body, { responseType: "blob" }),
  officialExcelAttrs: (shopId, categoryId) =>
    http.get("/excel/official-attrs", { params: { shop_id: shopId, category_id: categoryId } }),
  excelDocParse: (form) => http.post("/excel/doc-parse", form),
  excelGridCheck: (form) => http.post("/excel/grid-check", form),
  excelGridGenerateImages: (form) => http.post("/excel/grid-generate-images", form),
  excelGridRegenCopy: (form) => http.post("/excel/grid-regen-copy", form),
  excelGridInferFields: (form) => http.post("/excel/grid-infer-fields", form),
  excelGridSuggestTemplate: (form) => http.post("/excel/grid-suggest-template", form),
  excelGridPollImages: (form) => http.post("/excel/grid-poll-images", form),
  excelImportRows: (form) => http.post("/excel/import-rows", form),
  excelTemplateUrl: (style, listingTemplateId, extra = {}) => {
    const params = new URLSearchParams({ style: style || "lingxing" });
    if (listingTemplateId) params.set("listing_template_id", listingTemplateId);
    if (extra.categoryId) params.set("category_id", extra.categoryId);
    if (extra.shopId) params.set("shop_id", extra.shopId);
    if (extra.categoryName) params.set("category_name", extra.categoryName);
    return `/api/v1/excel/template?${params.toString()}`;
  },
  excelSmartTemplateUrl: (extra = {}) => {
    const params = new URLSearchParams();
    if (extra.categoryId) params.set("category_id", extra.categoryId);
    if (extra.shopId) params.set("shop_id", extra.shopId);
    if (extra.categoryName) params.set("category_name", extra.categoryName);
    return `/api/v1/excel/smart-template?${params.toString()}`;
  },
  photobank: (shopId, params) => http.get(`/shops/${shopId}/photobank`, { params }),
  learnDefaults: (shopId, body) => http.post(`/shops/${shopId}/online/learn-defaults`, body),
  learnTemplate: (shopId, body) => http.post(`/shops/${shopId}/online/learn-template`, body),

  drafts: (params) => http.get("/drafts", { params }),
  draft: (id) => http.get(`/drafts/${id}`),
  patchDraft: (id, body) => http.patch(`/drafts/${id}`, body),
  deleteDraft: (id) => http.delete(`/drafts/${id}`),
  publishDraft: (id) => http.post(`/drafts/${id}/publish`),
  publishMany: (draftIds) => http.post("/drafts/publish", { draft_ids: draftIds }),

  jobs: (params) => http.get("/jobs", { params }),
  retryJob: (id) => http.post(`/jobs/${id}/retry`),
};
