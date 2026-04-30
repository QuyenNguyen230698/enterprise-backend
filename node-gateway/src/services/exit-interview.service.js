const axios = require("axios");

const PYTHON_URL = process.env.PYTHON_SERVICE_URL || "http://python-app:8000";
const BASE = `${PYTHON_URL}/api/v1/exit-interview`;

function getUserId(reqUser) {
  const id = reqUser?.portal_user_id || reqUser?.id || null;
  return id != null ? String(id) : null;
}

function getUserName(reqUser) {
  return reqUser?.full_name || reqUser?.name || reqUser?.display_name || "Unknown";
}

const exitInterviewService = {
  async list(_reqUser, query = {}) {
    const params = {
      page: Number(query.page || 1),
      page_size: Number(query.page_size || 30),
    };
    if (query.status) params.status = query.status;
    if (query.tenant_id) params.tenant_id = query.tenant_id;
    if (query.created_by) params.created_by = query.created_by;
    if (query.employee_id) params.employee_id = query.employee_id;

    const res = await axios.get(BASE, { params });
    return res.data?.data || { items: [], total: 0, page: 1 };
  },

  async create(reqUser, payload = {}) {
    const body = {
      ...payload,
      tenant_id: payload.tenant_id || reqUser?.tenant_id || null,
    };
    const res = await axios.post(BASE, body);
    return res.data?.data || null;
  },

  async getById(_reqUser, id) {
    const res = await axios.get(`${BASE}/${id}`);
    return res.data?.data || null;
  },

  async takeAction(reqUser, id, payload = {}) {
    const body = {
      ...payload,
      actor_id: payload.actor_id || getUserId(reqUser),
      actor_name: payload.actor_name || getUserName(reqUser),
    };
    const res = await axios.post(`${BASE}/${id}/actions`, body);
    return res.data?.data || null;
  },
};

module.exports = exitInterviewService;
