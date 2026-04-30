const express = require("express");
const router = express.Router();
const c = require("../controllers/email-list.controller");
const { requirePermission } = require("../middleware/auth.middleware");

const perm = requirePermission("email-lists");

// List-level routes
router.get("/",           perm, c.list);
router.post("/",          perm, c.create);
router.put("/:id",        perm, c.update);
router.delete("/:id",     perm, c.remove);

// Export (before /:id to avoid conflict)
router.get("/:id/export", perm, c.exportCsv);

// Subscriber routes — specific paths before parameterized
router.post("/:id/subscribers/bulk-delete", perm, c.bulkDeleteSubscribers);
router.post("/:id/subscribers/bulk",        perm, c.bulkImportSubscribers);
router.post("/:id/import",                  perm, c.importSubscribers);
router.post("/:id/subscribers",             perm, c.addSubscriber);
router.put("/:id/subscribers/:subId",       perm, c.updateSubscriber);
router.delete("/:id/subscribers/:subId",    perm, c.deleteSubscriber);

// Upload config
router.get("/:id/cloudinary-config", perm, c.getUploadConfig);

// Detail — must be last to not shadow specific sub-paths
router.get("/:id",        perm, c.get);

module.exports = router;
