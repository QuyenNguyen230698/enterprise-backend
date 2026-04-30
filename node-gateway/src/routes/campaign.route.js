const express = require("express");
const router = express.Router();
const c = require("../controllers/campaign.controller");
const { requirePermission } = require("../middleware/auth.middleware");

const perm = requirePermission("email-lists");

router.get("/dashboard",               perm, c.dashboard);
router.get("/",                        perm, c.list);
router.post("/",                       perm, c.create);
router.get("/:id",                     perm, c.get);
router.put("/:id",                     perm, c.update);
router.delete("/:id",                  perm, c.remove);
router.post("/:id/load-recipients",    perm, c.loadRecipients);
router.post("/:id/send",               perm, c.send);
router.get("/:id/tracking-data",       perm, c.trackingData);

module.exports = router;
