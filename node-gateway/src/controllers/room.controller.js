const proxyService = require("../services/proxy.service");

const roomController = {
  async list(req, res) {
    try {
      const query = { ...req.query, portal_user_id: req.user.portal_user_id };
      const rooms = await proxyService.listRooms(query);
      res.json(rooms);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async create(req, res) {
    try {
      const room = await proxyService.createRoom(req.body);
      res.status(201).json(room);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async getById(req, res) {
    try {
      const room = await proxyService.getRoom(req.params.id);
      res.json(room);
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  },

  async update(req, res) {
    try {
      const room = await proxyService.updateRoom(req.params.id, req.body);
      res.json(room);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async remove(req, res) {
    try {
      await proxyService.deleteRoom(req.params.id);
      res.status(204).send();
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },
};

module.exports = roomController;
