const proxyService = require("../services/proxy.service");

const areaController = {
  async list(req, res) {
    try {
      const query = req.isSuperAdmin && req.query.tenant_id
        ? { tenant_id: req.query.tenant_id }
        : { portal_user_id: req.user.portal_user_id };
      const areas = await proxyService.listAreas(query);
      res.json(areas);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async create(req, res) {
    try {
      const area = await proxyService.createArea(req.body);
      res.status(201).json(area);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async getById(req, res) {
    try {
      const area = await proxyService.getArea(req.params.id);
      res.json(area);
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  },

  async update(req, res) {
    try {
      const area = await proxyService.updateArea(req.params.id, req.body);
      res.json(area);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async remove(req, res) {
    try {
      await proxyService.deleteArea(req.params.id);
      res.status(204).send();
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async getRooms(req, res) {
    try {
      const rooms = await proxyService.listAreaRooms(req.params.id);
      res.json(rooms);
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  },

  async createSharedAccess(req, res) {
    try {
      const record = await proxyService.createSharedAccess(req.body);
      res.status(201).json(record);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },
};

module.exports = areaController;
