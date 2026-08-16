import axios from "axios";

const http = axios.create({ baseURL: "/api/v1", withCredentials: true });

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const detail = error.response?.data?.detail;
    const message = typeof detail === "string" ? detail : error.message || "请求失败";
    return Promise.reject(new Error(message));
  },
);

export const api = {
  me: () => http.get("/auth/me"),
  login: (payload) => http.post("/auth/login", payload),
  register: (payload) => http.post("/auth/register", payload),
  logout: () => http.post("/auth/logout"),

  overview: () => http.get("/overview"),

  shops: () => http.get("/shops"),
  oauthStart: () => http.get("/alibaba/oauth/start"),
  bindEnvShop: (name) => http.post("/shops/bind-env", { name }),
  unbindShop: (shopId) => http.delete(`/shops/${shopId}`),
  saveDefaults: (shopId, body) => http.post(`/shops/${shopId}/defaults`, body),
  onlineProducts: (shopId, params) => http.get(`/shops/${shopId}/online`, { params }),
  categories: (shopId, parent) => http.get(`/shops/${shopId}/categories`, { params: { shop_id: shopId, parent } }),

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

  feed: (form) => http.post("/listings/feed", form),
  feedBatch: (form) => http.post("/listings/batch", form),
  batchProgress: (batchId) => http.get(`/batches/${batchId}`),

  excelStyles: () => http.get("/excel/styles"),
  excelPreview: (form) => http.post("/excel/preview", form),
  excelImport: (form) => http.post("/excel/import", form),
  excelTemplateUrl: (style, listingTemplateId, extra = {}) => {
    const params = new URLSearchParams({ style: style || "lingxing" });
    if (listingTemplateId) params.set("listing_template_id", listingTemplateId);
    if (extra.categoryId) params.set("category_id", extra.categoryId);
    if (extra.shopId) params.set("shop_id", extra.shopId);
    return `/api/v1/excel/template?${params.toString()}`;
  },
  cloneOnline: (shopId, body) => http.post(`/shops/${shopId}/online/clone`, body),
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
