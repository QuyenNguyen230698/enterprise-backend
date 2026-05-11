const express = require("express");
const router = express.Router();
const c = require("../controllers/hrm-document-template.controller");

router.get("/",       c.list);
router.post("/",      c.create);
router.get("/:id",    c.getById);
router.put("/:id",    c.update);
router.post("/:id/publish", c.publish);
router.delete("/:id", c.remove);

module.exports = router;
