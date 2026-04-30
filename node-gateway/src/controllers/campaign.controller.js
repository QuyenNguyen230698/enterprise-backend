const proxyService = require("../services/proxy.service");

const campaignController = {
  // GET /campaigns/dashboard
  async dashboard(req, res) {
    try {
      const dateRange = req.query.dateRange || 30;
      const data = await proxyService.getCampaignDashboard(req.user.portal_user_id, dateRange);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // GET /campaigns
  async list(req, res) {
    try {
      const data = await proxyService.listCampaigns(req.user.portal_user_id, req.query);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // GET /campaigns/:id
  async get(req, res) {
    try {
      const data = await proxyService.getCampaign(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /campaigns
  async create(req, res) {
    try {
      const { name, subject } = req.body;
      if (!name || !subject) {
        return res.status(422).json({ success: false, message: "Tên và tiêu đề campaign là bắt buộc" });
      }
      const data = await proxyService.createCampaign(req.user.portal_user_id, req.body);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // PUT /campaigns/:id
  async update(req, res) {
    try {
      const data = await proxyService.updateCampaign(req.params.id, req.user.portal_user_id, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // DELETE /campaigns/:id
  async remove(req, res) {
    try {
      const data = await proxyService.deleteCampaign(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /campaigns/:id/load-recipients
  async loadRecipients(req, res) {
    try {
      const data = await proxyService.loadCampaignRecipients(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /campaigns/:id/send
  async send(req, res) {
    try {
      const data = await proxyService.sendCampaign(req.params.id, req.user.portal_user_id, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // GET /campaigns/:id/tracking-data
  async trackingData(req, res) {
    try {
      const data = await proxyService.getCampaignTrackingData(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },
};

module.exports = campaignController;
