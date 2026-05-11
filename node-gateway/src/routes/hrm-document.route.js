const express = require("express");
const router = express.Router();
const c = require("../controllers/hrm-document.controller");

// Danh sách + tạo mới
router.get("/",  c.list);
router.post("/", c.create);

// Chi tiết
router.get("/:id", c.getById);

// Nộp biên bản (DRAFT → pending step 2)
router.post("/:id/submit", c.submit);

// Auto-save nội dung (DRAFT only)
router.patch("/:id/content", c.saveContent);

// Approve / Reject theo bước workflow
router.post("/:id/steps/:stepNumber/action", c.takeAction);

// Notify next signers
router.post("/:id/notify", c.notifyDocument);
router.delete("/:id", c.deleteDocument);

module.exports = router;
