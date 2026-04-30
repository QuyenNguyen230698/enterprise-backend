const proxyService = require("../services/proxy.service");

const userController = {
  // Trả về thông tin user đang đăng nhập từ JWT
  async me(req, res) {
    try {
      const user = await proxyService.getUserByPortalId(req.user.portal_user_id);
      res.json(user);
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  },

  // Trả về danh sách user cùng tenant — dùng cho chọn participants
  async tenantMembers(req, res) {
    try {
      const tenantId = req.user.tenant_id;
      if (!tenantId) {
        return res.status(403).json({ error: "No tenant_id in token." });
      }
      // Gọi thẳng endpoint /tenant-members với tenant_id — Python backend filter tại DB
      const members = await proxyService.listTenantMembers(tenantId);
      // Chỉ expose các field cần thiết cho client
      const safeMembers = members.map((u) => ({
        portal_user_id: u.portal_user_id,
        full_name: u.full_name || u.name,
        email: u.email,
        avatar_url: u.avatar_url,
        role: u.role,
      }));
      res.json(safeMembers);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async list(req, res) {
    try {
      let tenantId;
      if (req.isSuperAdmin) {
        // superAdmin không có tenant_id trong JWT — phải truyền qua query
        tenantId = req.query.tenant_id;
        if (!tenantId) return res.status(400).json({ error: "tenant_id query param required." });
      } else {
        tenantId = req.tenant_id;
        if (!tenantId) return res.status(403).json({ error: "No tenant_id in token." });
      }
      const users = await proxyService.listUsers(tenantId);
      res.json(users);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async upsert(req, res) {
    try {
      const user = await proxyService.upsertUser(req.body);
      res.status(201).json(user);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async getById(req, res) {
    try {
      const user = await proxyService.getUser(req.params.id);
      res.json(user);
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  },

  async getByPortalId(req, res) {
    try {
      const user = await proxyService.getUserByPortalId(req.params.portalId);
      res.json(user);
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  },

  async update(req, res) {
    try {
      const user = await proxyService.updateUser(req.params.id, req.body);
      res.json(user);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async remove(req, res) {
    try {
      await proxyService.request("delete", `/api/v1/users/${req.params.id}`);
      res.status(204).end();
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },
};

module.exports = userController;
