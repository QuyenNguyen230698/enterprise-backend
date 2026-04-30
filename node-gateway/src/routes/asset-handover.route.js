const express = require("express");
const router = express.Router();
const c = require("../controllers/asset-handover.controller");

router.get("/", c.list);
router.post("/", c.create);
router.get("/by-offboarding/:offboardingId", c.getByOffboarding);
router.get("/:id", c.getById);
router.put("/:id/assets", c.updateAssets);
router.post("/:id/actions", c.takeAction);

module.exports = router;
