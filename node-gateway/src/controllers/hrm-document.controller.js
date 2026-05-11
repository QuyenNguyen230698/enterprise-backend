/**
 * hrm-document.controller.js
 * Node Gateway → python-service proxy cho HRM Document Instances.
 * FE gọi:  /api/v1/hrm/documents/*  (qua authMiddleware)
 * Gateway forward: /api/v1/internal/hrm/documents/* (python-service)
 */
const axios = require("axios");
const notificationSocket = require("../sockets/notificationSocket");

const PYTHON_URL = process.env.PYTHON_SERVICE_URL || "http://python-app:8000";
const BASE = `${PYTHON_URL}/api/v1/internal/hrm/documents`;

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

  // ── GET /  Danh sách biên bản ─────────────────────────────────────────────
  async list(req, res) {
    try {
      const params = {
        tenant_id: req.user.tenant_id,
        page: req.query.page || 1,
        page_size: req.query.page_size || 20,
      };

      // Nếu user muốn xem "To Do" (những việc mình cần làm)
      if (req.query.todo === 'true') {
        params.assigned_to = String(req.user.portal_user_id || req.user.id || '');
      } else {
        // Nếu không phải admin → chỉ lấy biên bản của chính họ (mặc định)
        // Lưu ý: Logic này có thể thay đổi tùy theo yêu cầu (ví dụ: manager thấy hết)
        if (req.query.submitted_by) {
          params.submitted_by = req.query.submitted_by;
        }
      }

      if (req.query.status) {
        params.status = req.query.status;
      }
      const { data } = await axios.get(BASE, { params });
      res.json(data);
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể tải danh sách biên bản") });
    }
  },

  // ── GET /:id  Chi tiết biên bản ──────────────────────────────────────────
  async getById(req, res) {
    try {
      const { data } = await axios.get(`${BASE}/${req.params.id}`);
      res.json(data);
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không tìm thấy biên bản") });
    }
  },

  // ── POST /  Tạo biên bản từ template ────────────────────────────────────
  async create(req, res) {
    try {
      const payload = {
        ...req.body,
        tenant_id: req.user.tenant_id,
        actor_id:    String(req.user.portal_user_id || req.user.id || ""),
        actor_name:  req.user.name || req.user.full_name || "",
        actor_title: req.user.title || "",
        actor_dept:  req.user.department || req.user.dept_code || "",
      };
      const { data } = await axios.post(BASE, payload);
      res.status(201).json(data);
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể tạo biên bản") });
    }
  },

  // ── POST /:id/submit  Nộp biên bản (DRAFT → PENDING_STEP_2) ──────────────
  async submit(req, res) {
    try {
      const payload = {
        note:       req.body.note || "",
        actor_id:   String(req.user.portal_user_id || req.user.id || ""),
        actor_name: req.user.name || req.user.full_name || "",
      };
      const { data } = await axios.post(`${BASE}/${req.params.id}/submit`, payload);
      res.json(data);
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể nộp biên bản") });
    }
  },

  // ── PATCH /:id/content  Auto-save nội dung DRAFT ─────────────────────────
  async saveContent(req, res) {
    try {
      const { data } = await axios.patch(`${BASE}/${req.params.id}/content`, {
        contentBlocks: req.body.contentBlocks,
      });
      res.json(data);
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể lưu nội dung") });
    }
  },

  // ── POST /:id/steps/:stepNumber/action  Approve / Reject ─────────────────
  async takeAction(req, res) {
    try {
      const payload = {
        action:       req.body.action,
        note:         req.body.note || "",
        verify_token: req.body.verifyToken || req.body.verify_token || null,
        actor_id:     String(req.user.portal_user_id || req.user.id || ""),
        actor_name:   req.user.name || req.user.full_name || "",
      };
      const url = `${BASE}/${req.params.id}/steps/${req.params.stepNumber}/action`;
      const { data } = await axios.post(url, payload);
      res.json(data);
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Thao tác thất bại") });
    }
  },

  // ── POST /:id/notify  Gửi thông báo ─────────────────────────────────────
  async notify(req, res) {
    try {
      const { data } = await axios.post(`${BASE}/${req.params.id}/notify`);

      // Emit socket real-time
      if (data.success && Array.isArray(data.notifications)) {
        data.notifications.forEach(n => {
          notificationSocket.emitToUser(n.user_id, "notification:new", {
            _id: n.id,
            title: n.title,
            message: n.message,
            type: n.type,
            link: n.link,
            isRead: false,
            createdAt: n.created_at,
          });
        });
      }

      res.json(data);
    } catch (e) {
      // notify thường không block flow chính nếu lỗi socket
      res.json({ success: false, error: e.message });
    }
  },

  // ── DELETE /:id  Xóa biên bản ──────────────────────────────────────────
  async deleteDocument(req, res) {
    try {
      const { data } = await axios.delete(`${BASE}/${req.params.id}`);
      res.json(data);
    } catch (e) {
      res.status(e?.response?.status || 500).json({ error: errMsg(e, "Không thể xóa biên bản") });
    }
  },
};

module.exports = ctrl;
