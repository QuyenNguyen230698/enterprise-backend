const proxyService = require("../services/proxy.service");
const axios = require("axios");

const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || "http://localhost:8000";

const emailListController = {
  // GET /email-lists
  async list(req, res) {
    try {
      const data = await proxyService.listEmailLists(req.user.portal_user_id, req.query);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-lists
  async create(req, res) {
    try {
      if (!req.body.name) {
        return res.status(422).json({ success: false, message: "Tên danh sách là bắt buộc" });
      }
      const data = await proxyService.createEmailList(req.user.portal_user_id, req.body);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // PUT /email-lists/:id
  async update(req, res) {
    try {
      const data = await proxyService.updateEmailList(req.params.id, req.user.portal_user_id, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // DELETE /email-lists/:id
  async remove(req, res) {
    try {
      const data = await proxyService.deleteEmailList(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // GET /email-lists/:id/export — stream CSV directly
  async exportCsv(req, res) {
    try {
      const uid = encodeURIComponent(req.user.portal_user_id);
      const format = req.query.format || "csv";
      const url = `${PYTHON_SERVICE_URL}/api/v1/email-lists/${req.params.id}/export?portal_user_id=${uid}&format=${format}`;

      const upstream = await axios.get(url, { responseType: "stream" });

      res.setHeader("Content-Type", upstream.headers["content-type"] || "text/csv");
      res.setHeader("Content-Disposition", upstream.headers["content-disposition"] || `attachment; filename="export.csv"`);
      upstream.data.pipe(res);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // GET /email-lists/:id — detail + subscribers
  async get(req, res) {
    try {
      const data = await proxyService.getEmailList(req.params.id, req.user.portal_user_id, req.query);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-lists/:id/subscribers
  async addSubscriber(req, res) {
    try {
      const data = await proxyService.addSubscriber(req.params.id, req.user.portal_user_id, req.body);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // PUT /email-lists/:id/subscribers/:subId
  async updateSubscriber(req, res) {
    try {
      const data = await proxyService.updateSubscriber(req.params.id, req.params.subId, req.user.portal_user_id, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // DELETE /email-lists/:id/subscribers/:subId
  async deleteSubscriber(req, res) {
    try {
      const data = await proxyService.deleteSubscriber(req.params.id, req.params.subId, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-lists/:id/subscribers/bulk-delete
  async bulkDeleteSubscribers(req, res) {
    try {
      const data = await proxyService.bulkDeleteSubscribers(req.params.id, req.user.portal_user_id, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-lists/:id/subscribers/bulk
  async bulkImportSubscribers(req, res) {
    try {
      const data = await proxyService.bulkImportSubscribers(req.params.id, req.user.portal_user_id, req.body);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-lists/:id/import
  async importSubscribers(req, res) {
    try {
      const data = await proxyService.importSubscribers(req.params.id, req.user.portal_user_id, req.body);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // GET /email-lists/:id/cloudinary-config
  async getUploadConfig(req, res) {
    try {
      const data = await proxyService.getEmailListUploadConfig(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },
};

module.exports = emailListController;
