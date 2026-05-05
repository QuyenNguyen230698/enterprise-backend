const proxyService = require("../services/proxy.service");
const axios = require("axios");
const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || "http://localhost:8000";

function buildQs(portalUserId, extra = {}) {
  const params = new URLSearchParams({ portal_user_id: portalUserId, ...extra });
  return params.toString();
}

const recruitmentController = {

  // ─── Jobs ───────────────────────────────────────────────────────

  async listJobs(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id, req.query);
      const data = await proxyService.request("get", `/api/v1/recruitment/jobs?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async createJob(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("post", `/api/v1/recruitment/jobs?${qs}`, req.body);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async getJob(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("get", `/api/v1/recruitment/jobs/${req.params.id}?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async updateJob(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("patch", `/api/v1/recruitment/jobs/${req.params.id}?${qs}`, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async deleteJob(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("delete", `/api/v1/recruitment/jobs/${req.params.id}?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // ─── Inbox ──────────────────────────────────────────────────────

  async listInbox(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id, req.query);
      const data = await proxyService.request("get", `/api/v1/recruitment/inbox?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async getInboxEmail(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("get", `/api/v1/recruitment/inbox/${req.params.id}?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async patchInboxEmail(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("patch", `/api/v1/recruitment/inbox/${req.params.id}?${qs}`, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async deleteInboxEmail(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id, req.query);
      const data = await proxyService.request("delete", `/api/v1/recruitment/inbox/${req.params.id}?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async bulkDeleteInboxEmails(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("post", `/api/v1/recruitment/inbox/bulk-delete?${qs}`, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // ─── Pull ────────────────────────────────────────────────────────

  async pullInbox(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("post", `/api/v1/recruitment/inbox/pull?${qs}`, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // ─── Stats ──────────────────────────────────────────────────────

  async stats(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("get", `/api/v1/recruitment/stats?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // ─── Bulk Reply ──────────────────────────────────────────────────

  async bulkReply(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("post", `/api/v1/recruitment/bulk-reply?${qs}`, req.body);
      res.status(202).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async listReplies(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id, req.query);
      const data = await proxyService.request("get", `/api/v1/recruitment/replies?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async getBulkDetail(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("get", `/api/v1/recruitment/replies/bulk/${req.params.bulkId}?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },
  // ─── Auto-reply Rules ────────────────────────────────────────────

  async listAutoRules(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id, req.query);
      const data = await proxyService.request("get", `/api/v1/recruitment/auto-rules?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async createAutoRule(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("post", `/api/v1/recruitment/auto-rules?${qs}`, req.body);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async getAutoRule(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("get", `/api/v1/recruitment/auto-rules/${req.params.id}?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async updateAutoRule(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("patch", `/api/v1/recruitment/auto-rules/${req.params.id}?${qs}`, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async deleteAutoRule(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("delete", `/api/v1/recruitment/auto-rules/${req.params.id}?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async toggleAutoRule(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const data = await proxyService.request("post", `/api/v1/recruitment/auto-rules/${req.params.id}/toggle?${qs}`);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  async downloadAttachment(req, res) {
    try {
      const qs = buildQs(req.user.portal_user_id);
      const url = `${PYTHON_SERVICE_URL}/api/v1/recruitment/inbox/${req.params.id}/attachments/${req.params.index}?${qs}`;
      const upstream = await axios.get(url, { responseType: "stream" });
      res.setHeader("Content-Type", upstream.headers["content-type"] || "application/octet-stream");
      res.setHeader("Content-Disposition", upstream.headers["content-disposition"] || "attachment");
      if (upstream.headers["content-length"]) {
        res.setHeader("Content-Length", upstream.headers["content-length"]);
      }
      upstream.data.pipe(res);
    } catch (e) {
      const status = e.response?.status || 400;
      res.status(status).json({ success: false, message: e.message });
    }
  },
};

module.exports = recruitmentController;
