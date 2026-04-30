const proxyService = require("../services/proxy.service");

const profileController = {
  async get(req, res) {
    try {
      const data = await proxyService.getProfile(req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async update(req, res) {
    try {
      const data = await proxyService.updateProfile(req.user.portal_user_id, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async mySubscription(req, res) {
    try {
      const data = await proxyService.request(
        "get",
        `/api/v1/profile/subscriptions/my-subscription?portal_user_id=${encodeURIComponent(req.user.portal_user_id)}`
      );
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async uploadAvatar(req, res) {
    try {
      if (!req.file && (!req.files || req.files.length === 0)) {
        return res.status(400).json({ error: "No file uploaded" });
      }
      const file = req.file || req.files[0];
      const data = await proxyService.uploadAvatar(req.user.portal_user_id, file);
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async getSignature(req, res) {
    try {
      const data = await proxyService.getSignature(req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async saveSignature(req, res) {
    try {
      const data = await proxyService.saveSignature(req.user.portal_user_id, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async uploadSignature(req, res) {
    try {
      if (!req.file && req.body?.image_data) {
        const data = await proxyService.uploadSignatureFromBase64(req.user.portal_user_id, req.body.image_data);
        return res.json(data);
      }
      if (!req.file && (!req.files || req.files.length === 0)) {
        return res.status(400).json({ error: "No file uploaded" });
      }
      const file = req.file || req.files[0];
      const data = await proxyService.uploadSignature(req.user.portal_user_id, file);
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async scanSignature(req, res) {
    try {
      if (!req.file && req.body?.image_data) {
        const data = await proxyService.scanSignatureFromBase64(req.user.portal_user_id, req.body.image_data);
        return res.json(data);
      }
      if (!req.file && (!req.files || req.files.length === 0)) {
        return res.status(400).json({ error: "No file uploaded" });
      }
      const file = req.file || req.files[0];
      const data = await proxyService.scanSignature(req.user.portal_user_id, file);
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async deleteSignature(req, res) {
    try {
      const data = await proxyService.deleteSignature(req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },
};

module.exports = profileController;
