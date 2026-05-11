const axios = require("axios");

const PYTHON_URL = process.env.PYTHON_SERVICE_URL || "http://python-app:8000";
const BASE = `${PYTHON_URL}/api/v1/internal/hrm/document-templates`;

const ROLE_SUPER = "2000000001";
const ROLE_ADMIN = "2000000002";

function isAdmin(user) {
  return [ROLE_SUPER, ROLE_ADMIN].includes(user?.role_id);
}

function errMsg(e, fallback) {
  return (
    e?.response?.data?.detail ||
    e?.response?.data?.message ||
    e?.response?.data?.error ||
    e?.message ||
    fallback
  );
}

const ctrl = {
  async list(req, res) {
    try {
      const params = {
        tenant_id: req.user.tenant_id,
        ...(req.query.status ? { status: req.query.status } : {}),
      };
      const { data } = await axios.get(BASE, { params });
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể tải danh sách mẫu văn bản") });
    }
  },

  async getById(req, res) {
    try {
      const { data } = await axios.get(`${BASE}/${req.params.id}`);
      res.json({ data });
    } catch (e) {
      const status = e?.response?.status || 500;
      res.status(status).json({ error: errMsg(e, "Không tìm thấy mẫu văn bản") });
    }
  },

  async create(req, res) {
    if (!isAdmin(req.user)) return res.status(403).json({ error: "Chỉ admin mới được tạo mẫu văn bản" });
    try {
      const params = {
        tenant_id: req.user.tenant_id,
        created_by: req.user.portal_user_id || req.user.id,
      };
      const { data } = await axios.post(BASE, req.body, { params });
      res.status(201).json({ data });
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể tạo mẫu văn bản") });
    }
  },

  async update(req, res) {
    if (!isAdmin(req.user)) return res.status(403).json({ error: "Chỉ admin mới được cập nhật mẫu văn bản" });
    try {
      const { data } = await axios.put(`${BASE}/${req.params.id}`, req.body);
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể cập nhật mẫu văn bản") });
    }
  },

  async publish(req, res) {
    if (!isAdmin(req.user)) return res.status(403).json({ error: "Chỉ admin mới được xuất bản mẫu văn bản" });
    try {
      const { data } = await axios.post(`${BASE}/${req.params.id}/publish`);
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể xuất bản mẫu văn bản") });
    }
  },

  async remove(req, res) {
    if (!isAdmin(req.user)) return res.status(403).json({ error: "Chỉ admin mới được xóa mẫu văn bản" });
    try {
      await axios.delete(`${BASE}/${req.params.id}`);
      res.status(204).end();
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể xóa mẫu văn bản") });
    }
  },
};

module.exports = ctrl;
