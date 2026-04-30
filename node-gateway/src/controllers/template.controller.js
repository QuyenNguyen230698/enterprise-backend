const proxyService = require("../services/proxy.service");

const templateController = {
  // GET /templates/my-templates
  async listMyTemplates(req, res) {
    try {
      const data = await proxyService.listMyTemplates(req.user.portal_user_id, req.query);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // GET /templates/:id
  async get(req, res) {
    try {
      const data = await proxyService.getTemplate(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /templates
  async create(req, res) {
    try {
      const { name, description, category, jsonData, json_data, htmlCache, html_snapshot } = req.body;
      if (!name) {
        return res.status(422).json({ success: false, message: "Tên template là bắt buộc" });
      }
      const payload = {
        name,
        description,
        category,
        json_data: jsonData ?? json_data ?? null,
        html_snapshot: htmlCache ?? html_snapshot ?? null,
      };
      const data = await proxyService.createTemplate(req.user.portal_user_id, payload);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // PUT /templates/:id
  async update(req, res) {
    try {
      const { name, description, category, jsonData, json_data, htmlCache, html_snapshot } = req.body;
      const payload = {
        ...(name !== undefined && { name }),
        ...(description !== undefined && { description }),
        ...(category !== undefined && { category }),
        ...((jsonData !== undefined || json_data !== undefined) && { json_data: jsonData ?? json_data }),
        ...((htmlCache !== undefined || html_snapshot !== undefined) && { html_snapshot: htmlCache ?? html_snapshot }),
      };
      const data = await proxyService.updateTemplate(req.params.id, req.user.portal_user_id, payload);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // DELETE /templates/:id
  async remove(req, res) {
    try {
      const data = await proxyService.deleteTemplate(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /templates/:id/duplicate
  async duplicate(req, res) {
    try {
      const data = await proxyService.duplicateTemplate(req.params.id, req.user.portal_user_id);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /templates/:id/use
  async use(req, res) {
    try {
      const data = await proxyService.incrementTemplateUsage(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },
};

module.exports = templateController;
