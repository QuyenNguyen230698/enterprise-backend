const express = require("express");
const router = express.Router();
const multer = require("multer");
const c = require("../controllers/profile.controller");

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 20 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    if (/^image\/(jpeg|png)$/.test(file.mimetype)) cb(null, true);
    else cb(new Error("Only png, jpg, jpeg allowed"));
  },
});

router.get("/", c.get);
router.put("/", c.update);
router.post("/upload-avatar", upload.single("file"), c.uploadAvatar);
router.get("/signature", c.getSignature);
router.put("/signature", c.saveSignature);
router.delete("/signature", c.deleteSignature);
router.post("/upload-signature", upload.single("file"), c.uploadSignature);
router.post("/scan-signature", upload.single("file"), c.scanSignature);
router.get("/subscriptions/my-subscription", c.mySubscription);

module.exports = router;
