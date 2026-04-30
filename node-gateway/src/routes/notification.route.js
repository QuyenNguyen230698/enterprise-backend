const express = require("express");
const router = express.Router();
const c = require("../controllers/notification.controller");
const { requirePermission } = require("../middleware/auth.middleware");

// IMPORTANT: specific paths must come before parameterized routes
router.get("/unread-count",  requirePermission("notifications"), c.unreadCount);
router.get("/",              requirePermission("notifications"), c.list);
router.put("/read-all",      requirePermission("notifications"), c.markAllRead);
router.put("/:id/read",      requirePermission("notifications"), c.markRead);
router.delete("/:id",        requirePermission("notifications"), c.remove);

module.exports = router;
