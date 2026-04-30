const assetHandoverService = require("../services/asset-handover.service");

const assetHandoverController = {
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
      const data = await assetHandoverService.list(req.user, req.query || {});
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: assetHandoverController._errMessage(e, "Không thể tải danh sách biên bản bàn giao"),
      });
    }
  },

  async create(req, res) {
    try {
      const data = await assetHandoverService.create(req.user, req.body || {});
      res.status(201).json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: assetHandoverController._errMessage(e, "Không thể tạo biên bản bàn giao"),
      });
    }
  },

  async getById(req, res) {
    try {
      const data = await assetHandoverService.getById(req.user, req.params.id);
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: assetHandoverController._errMessage(e, "Không thể tải biên bản bàn giao"),
      });
    }
  },

  async updateAssets(req, res) {
    try {
      const assets = req.body?.assets || [];
      const data = await assetHandoverService.updateAssets(req.user, req.params.id, assets);
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: assetHandoverController._errMessage(e, "Không thể cập nhật danh sách tài sản"),
      });
    }
  },

  async takeAction(req, res) {
    try {
      const data = await assetHandoverService.takeAction(req.user, req.params.id, req.body || {});
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: assetHandoverController._errMessage(e, "Thao tác thất bại"),
      });
    }
  },

  async getByOffboarding(req, res) {
    try {
      const data = await assetHandoverService.getByOffboarding(req.user, req.params.offboardingId);
      res.json({ data });
    } catch (e) {
      res.status(e?.response?.status || 400).json({
        error: assetHandoverController._errMessage(e, "Không thể tải biên bản theo offboarding"),
      });
    }
  },
};

module.exports = assetHandoverController;
