const axios = require("axios");
require("dotenv").config();

const PYTHON_SERVICE_URL =
  process.env.PYTHON_SERVICE_URL || "http://localhost:8000";

/**
 * Generic request helper — handles axios calls + error normalization.
 */
class ProxyError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, data = null) {
  try {
    const config = { method, url: `${PYTHON_SERVICE_URL}${path}` };
    if (data) config.data = data;
    const response = await axios(config);
    return response.data;
  } catch (error) {
    let detail = error.response?.data?.detail || error.message;
    if (typeof detail === "object") detail = JSON.stringify(detail);
    throw new ProxyError(detail, error.response?.status || 500);
  }
}

const proxyService = {
  request, // expose for ad-hoc use in route files
  // ─── Areas ───────────────────────────────────────────────────
  async listAreas(query = {}) {
    const params = new URLSearchParams(query).toString();
    return request("get", `/api/v1/areas/${params ? "?" + params : ""}`);
  },
  async createArea(data) {
    return request("post", "/api/v1/areas/", data);
  },
  async getArea(id) {
    return request("get", `/api/v1/areas/${id}`);
  },
  async updateArea(id, data) {
    return request("put", `/api/v1/areas/${id}`, data);
  },
  async deleteArea(id) {
    return request("delete", `/api/v1/areas/${id}`);
  },
  async listAreaRooms(id) {
    return request("get", `/api/v1/areas/${id}/rooms`);
  },
  async createSharedAccess(data) {
    return request("post", "/api/v1/areas/shared-access", data);
  },

  // ─── Rooms ───────────────────────────────────────────────────
  async listRooms(query = {}) {
    const params = new URLSearchParams(query).toString();
    return request("get", `/api/v1/rooms/${params ? "?" + params : ""}`);
  },
  async createRoom(data) {
    return request("post", "/api/v1/rooms/", data);
  },
  async getRoom(id) {
    return request("get", `/api/v1/rooms/${id}`);
  },
  async updateRoom(id, data) {
    return request("put", `/api/v1/rooms/${id}`, data);
  },
  async deleteRoom(id) {
    return request("delete", `/api/v1/rooms/${id}`);
  },

  // ─── Users ───────────────────────────────────────────────────
  async listTenantMembers(tenantId) {
    return request("get", `/api/v1/users/tenant-members?tenant_id=${encodeURIComponent(tenantId)}`);
  },
  async listUsers(tenantId) {
    return request("get", `/api/v1/users/?tenant_id=${encodeURIComponent(tenantId)}`);
  },
  async upsertUser(data) {
    return request("post", "/api/v1/users/", data);
  },
  async getUser(id) {
    return request("get", `/api/v1/users/${id}`);
  },
  async getUserByPortalId(portalId) {
    return request("get", `/api/v1/users/portal/${portalId}`);
  },
  async updateUser(id, data) {
    return request("put", `/api/v1/users/${id}`, data);
  },

  // ─── Meetings ────────────────────────────────────────────────
  async listMeetings(query = {}) {
    const params = new URLSearchParams(query).toString();
    return request("get", `/api/v1/meetings/${params ? "?" + params : ""}`);
  },
  async createMeeting(data) {
    return request("post", "/api/v1/meetings/", data);
  },
  async getMeeting(id) {
    return request("get", `/api/v1/meetings/${id}`);
  },
  async updateMeeting(id, data) {
    return request("put", `/api/v1/meetings/${id}`, data);
  },
  async deleteMeeting(id) {
    return request("delete", `/api/v1/meetings/${id}`);
  },
  async cancelMeeting(id) {
    return request("patch", `/api/v1/meetings/${id}/cancel`);
  },

  // ─── Meeting Invites ─────────────────────────────────────────
  async listInvites(meetingId) {
    return request("get", `/api/v1/meetings/${meetingId}/invites`);
  },
  async addInvite(meetingId, data) {
    return request("post", `/api/v1/meetings/${meetingId}/invites`, data);
  },
  async respondInvite(inviteId, data) {
    return request("put", `/api/v1/meetings/invites/${inviteId}/respond`, data);
  },

  // ─── Email Config ─────────────────────────────────────────────
  async listEmailConfigs(portalUserId) {
    return request("get", `/api/v1/email-config?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async createEmailConfig(portalUserId, data) {
    return request("post", `/api/v1/email-config?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async updateEmailConfig(id, portalUserId, data) {
    return request("put", `/api/v1/email-config/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async deleteEmailConfig(id, portalUserId) {
    return request("delete", `/api/v1/email-config/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async setDefaultEmailConfig(id, portalUserId) {
    return request("post", `/api/v1/email-config/${id}/set-default?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async testEmailConfig(id, portalUserId, data) {
    return request("post", `/api/v1/email-config/${id}/test?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },

  // ─── Profile ──────────────────────────────────────────────────
  async getProfile(portalUserId) {
    return request("get", `/api/v1/profile?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async updateProfile(portalUserId, data) {
    return request("put", `/api/v1/profile?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async uploadAvatar(portalUserId, file) {
    const FormData = require("form-data");
    const axios = require("axios");
    const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || "http://localhost:8000";
    const form = new FormData();
    form.append("file", file.buffer, { filename: file.originalname, contentType: file.mimetype });
    const response = await axios.post(
      `${PYTHON_SERVICE_URL}/api/v1/profile/upload-avatar?portal_user_id=${encodeURIComponent(portalUserId)}`,
      form,
      { headers: form.getHeaders() }
    );
    return response.data;
  },
  async getSignature(portalUserId) {
    return request("get", `/api/v1/profile/signature?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async saveSignature(portalUserId, data) {
    return request("put", `/api/v1/profile/signature?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async deleteSignature(portalUserId) {
    return request("delete", `/api/v1/profile/signature?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async uploadSignature(portalUserId, file) {
    const FormData = require("form-data");
    const axios = require("axios");
    const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || "http://localhost:8000";
    const form = new FormData();
    form.append("file", file.buffer, { filename: file.originalname, contentType: file.mimetype });
    const response = await axios.post(
      `${PYTHON_SERVICE_URL}/api/v1/profile/upload-signature?portal_user_id=${encodeURIComponent(portalUserId)}`,
      form,
      { headers: form.getHeaders() }
    );
    return response.data;
  },
  async uploadSignatureFromBase64(portalUserId, imageData) {
    return request(
      "post",
      `/api/v1/profile/upload-signature?portal_user_id=${encodeURIComponent(portalUserId)}`,
      { image_data: imageData }
    );
  },
  async scanSignature(portalUserId, file) {
    const FormData = require("form-data");
    const axios = require("axios");
    const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || "http://localhost:8000";
    const form = new FormData();
    form.append("file", file.buffer, { filename: file.originalname, contentType: file.mimetype });
    const response = await axios.post(
      `${PYTHON_SERVICE_URL}/api/v1/profile/scan-signature?portal_user_id=${encodeURIComponent(portalUserId)}`,
      form,
      { headers: form.getHeaders() }
    );
    return response.data;
  },
  async scanSignatureFromBase64(portalUserId, imageData) {
    return request(
      "post",
      `/api/v1/profile/scan-signature?portal_user_id=${encodeURIComponent(portalUserId)}`,
      { image_data: imageData }
    );
  },

  // ─── Email Lists ─────────────────────────────────────────────
  async listEmailLists(portalUserId, query = {}) {
    const params = new URLSearchParams({ ...query, portal_user_id: portalUserId }).toString();
    return request("get", `/api/v1/email-lists?${params}`);
  },
  async getEmailList(id, portalUserId, query = {}) {
    const params = new URLSearchParams({ ...query, portal_user_id: portalUserId }).toString();
    return request("get", `/api/v1/email-lists/${id}?${params}`);
  },
  async createEmailList(portalUserId, data) {
    return request("post", `/api/v1/email-lists?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async updateEmailList(id, portalUserId, data) {
    return request("put", `/api/v1/email-lists/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async deleteEmailList(id, portalUserId) {
    return request("delete", `/api/v1/email-lists/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async addSubscriber(listId, portalUserId, data) {
    return request("post", `/api/v1/email-lists/${listId}/subscribers?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async updateSubscriber(listId, subId, portalUserId, data) {
    return request("put", `/api/v1/email-lists/${listId}/subscribers/${subId}?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async deleteSubscriber(listId, subId, portalUserId) {
    return request("delete", `/api/v1/email-lists/${listId}/subscribers/${subId}?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async bulkDeleteSubscribers(listId, portalUserId, data) {
    return request("post", `/api/v1/email-lists/${listId}/subscribers/bulk-delete?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async bulkImportSubscribers(listId, portalUserId, data) {
    return request("post", `/api/v1/email-lists/${listId}/subscribers/bulk?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async importSubscribers(listId, portalUserId, data) {
    return request("post", `/api/v1/email-lists/${listId}/import?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async getEmailListUploadConfig(listId, portalUserId) {
    return request("get", `/api/v1/email-lists/${listId}/cloudinary-config?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },

  // ─── Templates ───────────────────────────────────────────────
  async listMyTemplates(portalUserId, query = {}) {
    const params = new URLSearchParams({ ...query, portal_user_id: portalUserId }).toString();
    return request("get", `/api/v1/templates/my-templates?${params}`);
  },
  async getTemplate(id, portalUserId) {
    return request("get", `/api/v1/templates/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async createTemplate(portalUserId, data) {
    return request("post", `/api/v1/templates?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async updateTemplate(id, portalUserId, data) {
    return request("put", `/api/v1/templates/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async deleteTemplate(id, portalUserId) {
    return request("delete", `/api/v1/templates/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async duplicateTemplate(id, portalUserId) {
    return request("post", `/api/v1/templates/${id}/duplicate?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async incrementTemplateUsage(id, portalUserId) {
    return request("post", `/api/v1/templates/${id}/use?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },

  // ─── Campaigns ───────────────────────────────────────────────
  async getCampaignDashboard(portalUserId, dateRange) {
    return request("get", `/api/v1/campaigns/dashboard?portal_user_id=${encodeURIComponent(portalUserId)}&dateRange=${dateRange}`);
  },
  async listCampaigns(portalUserId, query = {}) {
    const params = new URLSearchParams({ ...query, portal_user_id: portalUserId }).toString();
    return request("get", `/api/v1/campaigns?${params}`);
  },
  async getCampaign(id, portalUserId) {
    return request("get", `/api/v1/campaigns/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async createCampaign(portalUserId, data) {
    return request("post", `/api/v1/campaigns?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async updateCampaign(id, portalUserId, data) {
    return request("put", `/api/v1/campaigns/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async deleteCampaign(id, portalUserId) {
    return request("delete", `/api/v1/campaigns/${id}?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async loadCampaignRecipients(id, portalUserId) {
    return request("post", `/api/v1/campaigns/${id}/load-recipients?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async sendCampaign(id, portalUserId, data) {
    return request("post", `/api/v1/campaigns/${id}/send?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async getCampaignTrackingData(id, portalUserId) {
    return request("get", `/api/v1/campaigns/${id}/tracking-data?portal_user_id=${encodeURIComponent(portalUserId)}`);
  },
  async validateEmailCapacity(portalUserId, data) {
    return request("post", `/api/v1/email-config/validate-capacity?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async sendTemplateTest(portalUserId, data) {
    return request("post", `/api/v1/admin/system-email-config/send-template-test?portal_user_id=${encodeURIComponent(portalUserId)}`, data);
  },
  async publicSendTest(data) {
    return request("post", `/api/v1/public/email/send-test`, data);
  },

  // ─── Notifications ───────────────────────────────────────────
  async listNotifications(portalUserId, tenantId, query = {}) {
    const params = new URLSearchParams({ ...query, portal_user_id: portalUserId, tenant_id: tenantId }).toString();
    return request("get", `/api/v1/notifications?${params}`);
  },
  async getUnreadCount(portalUserId, tenantId) {
    return request("get", `/api/v1/notifications/unread-count?portal_user_id=${encodeURIComponent(portalUserId)}&tenant_id=${encodeURIComponent(tenantId)}`);
  },
  async markNotificationRead(id, portalUserId, tenantId) {
    return request("put", `/api/v1/notifications/${id}/read?portal_user_id=${encodeURIComponent(portalUserId)}&tenant_id=${encodeURIComponent(tenantId)}`);
  },
  async markAllNotificationsRead(portalUserId, tenantId) {
    return request("put", `/api/v1/notifications/read-all?portal_user_id=${encodeURIComponent(portalUserId)}&tenant_id=${encodeURIComponent(tenantId)}`);
  },
  async deleteNotification(id, portalUserId, tenantId) {
    return request("delete", `/api/v1/notifications/${id}?portal_user_id=${encodeURIComponent(portalUserId)}&tenant_id=${encodeURIComponent(tenantId)}`);
  },
  async createNotification(data) {
    return request("post", `/api/v1/notifications`, data);
  },

  // Internal & Email Actions
  async internalSendInvite(inviteId) {
    return request("post", `/api/v1/meetings/internal/send-invite/${inviteId}`);
  },
  async internalCleanupZoom() {
    return request("post", `/api/v1/meetings/internal/cleanup-zoom-meetings`);
  },
  async respondInviteGet(inviteId, query) {
    const params = new URLSearchParams(query).toString();
    return request(
      "get",
      `/api/v1/meetings/invites/${inviteId}/respond?${params}`,
    );
  },
};

module.exports = proxyService;
