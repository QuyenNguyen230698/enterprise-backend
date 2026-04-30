const jobHandoverService = require("../services/job-handover.service");

const jobHandoverController = {
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
      const data = await jobHandoverService.list(req.user, req.query || {});
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: jobHandoverController._errMessage(e, "Không thể tải danh sách biên bản bàn giao công việc"),
      });
    }
  },

  async create(req, res) {
    try {
      const data = await jobHandoverService.create(req.user, req.body || {});
      res.status(201).json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: jobHandoverController._errMessage(e, "Không thể tạo biên bản bàn giao công việc"),
      });
    }
  },

  async getById(req, res) {
    try {
      const data = await jobHandoverService.getById(req.user, req.params.id);
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: jobHandoverController._errMessage(e, "Không thể tải biên bản bàn giao công việc"),
      });
    }
  },

  async takeAction(req, res) {
    try {
      const data = await jobHandoverService.takeAction(req.user, req.params.id, req.body || {});
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: jobHandoverController._errMessage(e, "Thao tác thất bại"),
      });
    }
  },
};

module.exports = jobHandoverController;
