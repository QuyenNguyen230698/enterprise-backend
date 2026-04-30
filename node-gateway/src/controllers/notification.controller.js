const proxyService = require("../services/proxy.service");

const notificationController = {
  // GET /notifications
  async list(req, res) {
    try {
      const { portal_user_id, tenant_id } = req.user;
      const data = await proxyService.listNotifications(portal_user_id, tenant_id, req.query);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // GET /notifications/unread-count
  async unreadCount(req, res) {
    try {
      const { portal_user_id, tenant_id } = req.user;
      const data = await proxyService.getUnreadCount(portal_user_id, tenant_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // PUT /notifications/:id/read
  async markRead(req, res) {
    try {
      const { portal_user_id, tenant_id } = req.user;
      const data = await proxyService.markNotificationRead(req.params.id, portal_user_id, tenant_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // PUT /notifications/read-all
  async markAllRead(req, res) {
    try {
      const { portal_user_id, tenant_id } = req.user;
      const data = await proxyService.markAllNotificationsRead(portal_user_id, tenant_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // DELETE /notifications/:id
  async remove(req, res) {
    try {
      const { portal_user_id, tenant_id } = req.user;
      const data = await proxyService.deleteNotification(req.params.id, portal_user_id, tenant_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },
};

module.exports = notificationController;
