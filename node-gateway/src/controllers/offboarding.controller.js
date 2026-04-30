const offboardingService = require("../services/offboarding.service");
const axios = require("axios");
const notificationSocket = require("../sockets/notificationSocket");

const PYTHON_URL = process.env.PYTHON_SERVICE_URL || "http://python-app:8000";

const offboardingController = {
  _errMessage(e, fallback) {
    return (
      e?.response?.data?.detail ||
      e?.response?.data?.message ||
      e?.response?.data?.error ||
      e?.message ||
      fallback
    );
  },

  async list(req, res) {
    try {
      const data = await offboardingService.list(req.user, req.query || {});
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể tải danh sách đơn") });
    }
  },

  async create(req, res) {
    try {
      const created = await offboardingService.create(req.user, req.body || {});
      if (created?.error === "FORBIDDEN") {
        return res.status(403).json({ error: created?.message || "Không có quyền tạo đơn" });
      }
      res.status(201).json({ data: created });
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể tạo đơn") });
    }
  },

  async getById(req, res) {
    try {
      const result = await offboardingService.getById(req.user, req.params.id);
      if (result === "FORBIDDEN") return res.status(403).json({ error: "Không có quyền truy cập đơn này" });
      if (!result) return res.status(404).json({ error: "Không tìm thấy đơn" });
      res.json({ data: result });
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể tải thông tin đơn") });
    }
  },

  async takeAction(req, res) {
    try {
      const result = await offboardingService.takeAction(
        req.user,
        req.params.id,
        Number(req.params.stepNumber),
        req.body || {}
      );
      if (result.error === "NOT_FOUND") return res.status(404).json({ error: "Không tìm thấy đơn" });
      if (result.error === "FORBIDDEN") return res.status(403).json({ error: result.message || "Không có quyền thao tác" });
      if (result.error === "MISSING_SIGNATURE") return res.status(400).json({ error: "Bạn cần tạo chữ ký SignHub trước khi phê duyệt offboarding." });
      res.json(result);
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Thao tác thất bại") });
    }
  },

  async confirmHandover(req, res) {
    try {
      const result = await offboardingService.confirmHandover(
        req.user,
        req.params.id,
        req.params.hoKey,
        req.body?.notes
      );
      if (result.error === "NOT_FOUND") return res.status(404).json({ error: "Không tìm thấy đơn" });
      if (result.error === "FORBIDDEN") return res.status(403).json({ error: result.message || "Không có quyền thao tác" });
      if (result.error === "MISSING_SIGNATURE") return res.status(400).json({ error: "Bạn cần tạo chữ ký SignHub trước khi phê duyệt offboarding." });
      if (result.error === "BAD_REQUEST") return res.status(400).json({ error: "Handover key không hợp lệ" });
      res.json(result);
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể xác nhận bàn giao") });
    }
  },

  async handoverTimelineAction(req, res) {
    try {
      const result = await offboardingService.handoverTimelineAction(
        req.user,
        req.params.id,
        req.params.hoKey,
        req.body || {}
      );
      if (result.error === "NOT_FOUND") return res.status(404).json({ error: "Không tìm thấy đơn" });
      if (result.error === "FORBIDDEN") return res.status(403).json({ error: result.message || "Không có quyền thao tác" });
      if (result.error === "BAD_REQUEST") return res.status(400).json({ error: result.message || "Dữ liệu không hợp lệ" });
      if (result.error === "MISSING_SIGNATURE") return res.status(400).json({ error: "Bạn cần tạo chữ ký SignHub trước khi ký/xác nhận biên bản." });
      res.json(result);
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể thao tác timeline biên bản") });
    }
  },

  async rejectHandover(req, res) {
    try {
      const result = await offboardingService.rejectHandover(
        req.user,
        req.params.id,
        req.params.hoKey,
        req.body?.reason
      );
      if (result.error === "NOT_FOUND") return res.status(404).json({ error: "Không tìm thấy đơn" });
      if (result.error === "FORBIDDEN") return res.status(403).json({ error: result.message || "Không có quyền thao tác" });
      if (result.error === "MISSING_SIGNATURE") return res.status(400).json({ error: "Bạn cần tạo chữ ký SignHub trước khi phê duyệt offboarding." });
      if (result.error === "BAD_REQUEST") return res.status(400).json({ error: result.message || "Dữ liệu không hợp lệ" });
      res.json(result);
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể reject bàn giao") });
    }
  },

  async saveHandoverContent(req, res) {
    try {
      const result = await offboardingService.saveHandoverContent(
        req.user,
        req.params.id,
        req.params.hoKey,
        req.body?.content
      );
      if (result.error === "NOT_FOUND") return res.status(404).json({ error: "Không tìm thấy đơn" });
      if (result.error === "FORBIDDEN") return res.status(403).json({ error: result.message || "Không có quyền thao tác" });
      res.json(result);
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể lưu nội dung biên bản") });
    }
  },

  async resetHandover(req, res) {
    try {
      const result = await offboardingService.resetHandover(req.user, req.params.id, req.params.hoKey, req.body?.reason);
      if (result.error === "NOT_FOUND") return res.status(404).json({ error: "Không tìm thấy đơn" });
      if (result.error === "FORBIDDEN") return res.status(403).json({ error: result.message || "Không có quyền thao tác" });
      res.json(result);
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể reset biên bản") });
    }
  },

  async overrideReturn(req, res) {
    try {
      const result = await offboardingService.overrideReturn(req.user, req.params.id, req.body?.reason);
      if (result.error === "NOT_FOUND") return res.status(404).json({ error: "Không tìm thấy đơn" });
      if (result.error === "FORBIDDEN") return res.status(403).json({ error: "Không có quyền thao tác" });
      if (result.error === "MISSING_SIGNATURE") return res.status(400).json({ error: "Bạn cần tạo chữ ký SignHub trước khi phê duyệt offboarding." });
      res.json(result);
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Thao tác thất bại") });
    }
  },

  async notify(req, res) {
    try {
      const { id } = req.params;
      const { step_number, action, note, extra } = req.body || {};

      // Gọi python-service tạo notification trong DB
      const pyRes = await axios.post(
        `${PYTHON_URL}/api/v1/internal/offboarding/processes/${id}/notify`,
        { step_number, action, note, extra }
      );
      const notifications = pyRes.data;

      // Emit socket real-time cho từng notification vừa tạo
      // Python trả về { success, notifications: [{user_id, tenant_id, ...}] }
      if (Array.isArray(notifications?.notifications)) {
        for (const n of notifications.notifications) {
          notificationSocket.emitToUser(n.user_id, "notification:new", {
            _id: n.id,
            title: n.title,
            message: n.message,
            type: n.type,
            link: n.link,
            isRead: false,
            createdAt: n.created_at,
          });
        }
      }

      res.json({ success: true });
    } catch (e) {
      // notify không block flow chính
      res.json({ success: false, error: e.message });
    }
  },

  async resendConfirmation(req, res) {
    try {
      const result = await offboardingService.resendConfirmation(req.user, req.params.id);
      if (result.error === "NOT_FOUND") return res.status(404).json({ error: "Không tìm thấy đơn" });
      if (result.error === "FORBIDDEN") return res.status(403).json({ error: "Không có quyền thao tác" });
      res.json(result);
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: offboardingController._errMessage(e, "Không thể gửi lại email xác nhận"),
      });
    }
  },

  async listApprovalLogs(req, res) {
    try {
      const data = await offboardingService.listApprovalLogs(req.user, req.query || {});
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({ error: offboardingController._errMessage(e, "Không thể tải lịch sử ký duyệt") });
    }
  },

};

module.exports = offboardingController;
