const express = require("express");
const router = express.Router();
const c = require("../controllers/email-config.controller");
const { requirePermission } = require("../middleware/auth.middleware");

router.post("/validate-capacity", requirePermission("email-lists"), c.validateCapacity);
router.get("/", requirePermission("email-config"), c.list);
router.post("/", requirePermission("email-config"), c.create);
router.put("/:id", requirePermission("email-config"), c.update);
router.delete("/:id", requirePermission("email-config"), c.remove);
router.post("/:id/set-default", requirePermission("email-config"), c.setDefault);
router.post("/:id/test", requirePermission("email-config"), c.test);

module.exports = router;
