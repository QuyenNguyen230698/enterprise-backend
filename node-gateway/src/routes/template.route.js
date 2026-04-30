const express = require("express");
const router = express.Router();
const c = require("../controllers/template.controller");
const { requirePermission } = require("../middleware/auth.middleware");

// Route order matters — specific paths before parameterized ones
router.get("/my-templates",        requirePermission("templates"), c.listMyTemplates);
router.get("/:id",                 requirePermission("templates"), c.get);
router.post("/",                   requirePermission("templates"), c.create);
router.put("/:id",                 requirePermission("templates"), c.update);
router.delete("/:id",              requirePermission("templates"), c.remove);
router.post("/:id/duplicate",      requirePermission("templates"), c.duplicate);
router.post("/:id/use",            requirePermission("templates"), c.use);

module.exports = router;
