const exitInterviewService = require("../services/exit-interview.service");

const exitInterviewController = {
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
      const data = await exitInterviewService.list(req.user, req.query || {});
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: exitInterviewController._errMessage(e, "Không thể tải danh sách biên bản phỏng vấn nghỉ việc"),
      });
    }
  },

  async create(req, res) {
    try {
      const data = await exitInterviewService.create(req.user, req.body || {});
      res.status(201).json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: exitInterviewController._errMessage(e, "Không thể tạo biên bản phỏng vấn nghỉ việc"),
      });
    }
  },

  async getById(req, res) {
    try {
      const data = await exitInterviewService.getById(req.user, req.params.id);
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: exitInterviewController._errMessage(e, "Không thể tải biên bản phỏng vấn nghỉ việc"),
      });
    }
  },

  async takeAction(req, res) {
    try {
      const data = await exitInterviewService.takeAction(req.user, req.params.id, req.body || {});
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: exitInterviewController._errMessage(e, "Thao tác thất bại"),
      });
    }
  },
};

module.exports = exitInterviewController;
