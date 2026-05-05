const express = require("express");
const router = express.Router();
const c = require("../controllers/recruitment.controller");
const { requirePermission } = require("../middleware/auth.middleware");

const perm = requirePermission("recruitment");

// Stats
router.get("/stats",              perm, c.stats);

// Jobs
router.get("/jobs",               perm, c.listJobs);
router.post("/jobs",              perm, c.createJob);
router.get("/jobs/:id",           perm, c.getJob);
router.patch("/jobs/:id",         perm, c.updateJob);
router.delete("/jobs/:id",        perm, c.deleteJob);

// Inbox — static routes must come before /:id to avoid route conflict
router.post("/inbox/pull",        perm, c.pullInbox);
router.post("/inbox/bulk-delete", perm, c.bulkDeleteInboxEmails);
router.get("/inbox",              perm, c.listInbox);
router.get("/inbox/:id",          perm, c.getInboxEmail);
router.get("/inbox/:id/attachments/:index", perm, c.downloadAttachment);
router.patch("/inbox/:id",        perm, c.patchInboxEmail);
router.delete("/inbox/:id",       perm, c.deleteInboxEmail);

// Bulk Reply
router.post("/bulk-reply",                  perm, c.bulkReply);
router.get("/replies",                      perm, c.listReplies);
router.get("/replies/bulk/:bulkId",         perm, c.getBulkDetail);

// Auto-reply Rules
router.get("/auto-rules",                   perm, c.listAutoRules);
router.post("/auto-rules",                  perm, c.createAutoRule);
router.get("/auto-rules/:id",              perm, c.getAutoRule);
router.patch("/auto-rules/:id",            perm, c.updateAutoRule);
router.delete("/auto-rules/:id",           perm, c.deleteAutoRule);
router.post("/auto-rules/:id/toggle",      perm, c.toggleAutoRule);

module.exports = router;
