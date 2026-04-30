const express = require("express");
const router = express.Router();
const c = require("../controllers/exit-interview.controller");

router.get("/", c.list);
router.post("/", c.create);
router.get("/:id", c.getById);
router.post("/:id/actions", c.takeAction);

module.exports = router;
