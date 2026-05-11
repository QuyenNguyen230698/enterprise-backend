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

  async sendSignatureOtp(req, res) {
    try {
      const data = await proxyService.request("post", "/api/v1/profile/signature/send-otp", {
        portal_user_id: req.user.portal_user_id,
      });
      res.json(data);
    } catch (e) {
      res.status(e.status || 400).json({ error: e.message, detail: e.message });
    }
  },

  async proxySignatureImage(req, res) {
    // Proxy /static/* files through /api/v1/profile/signature-image?path=...
    // so Cloudflare (which blocks bare /static) passes them through.
    const filePath = req.query.path
    if (!filePath || typeof filePath !== "string") {
      return res.status(400).json({ error: "Missing path param" })
    }
    // Only allow signhub-signatures and avatars paths — prevent SSRF
    if (!/^\/?(static\/)?(signhub-signatures|avatars)\/[\w.\-]+\.png$/i.test(filePath)) {
      return res.status(400).json({ error: "Invalid path" })
    }
    const cleanPath = filePath.startsWith("/") ? filePath : `/${filePath}`
    const normalised = cleanPath.startsWith("/static/") ? cleanPath : `/static${cleanPath}`
    const PYTHON_URL = process.env.PYTHON_SERVICE_URL || "http://python-app:8000"
    try {
      const axios = require("axios")
      const upstream = await axios.get(`${PYTHON_URL}${normalised}`, { responseType: "arraybuffer" })
      res.set("Content-Type", upstream.headers["content-type"] || "image/png")
      res.set("Cache-Control", "public, max-age=31536000, immutable")
      res.send(Buffer.from(upstream.data))
    } catch (e) {
      res.status(e.response?.status || 404).json({ error: "Image not found" })
    }
  },

  async verifySignatureOtp(req, res) {
    try {
      const data = await proxyService.request("post", "/api/v1/profile/signature/verify-otp", {
        portal_user_id: req.user.portal_user_id,
        otp_code: req.body.otp_code,
      });
      res.json(data);
    } catch (e) {
      res.status(e.status || 400).json({ error: e.message, detail: e.message });
    }
  },
};

module.exports = profileController;
