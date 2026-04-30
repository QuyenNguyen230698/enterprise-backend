const express = require("express");
const router = express.Router();
const c = require("../controllers/offboarding.controller");

router.get("/processes", c.list);
router.post("/processes", c.create);
router.get("/processes/:id", c.getById);
router.post("/processes/:id/steps/:stepNumber/action", c.takeAction);
router.post("/processes/:id/handover/:hoKey/confirm", c.confirmHandover);
router.post("/processes/:id/handover/:hoKey/timeline-action", c.handoverTimelineAction);
router.post("/processes/:id/handover/:hoKey/reject", c.rejectHandover);
router.patch("/processes/:id/handover/:hoKey/content", c.saveHandoverContent);
router.post("/processes/:id/handover/:hoKey/reset", c.resetHandover);
router.post("/processes/:id/override/return-handover", c.overrideReturn);
router.post("/processes/:id/notify", c.notify);
router.post("/processes/:id/resend-confirmation", c.resendConfirmation);
router.get("/sign-hub/approval-logs", c.listApprovalLogs);

module.exports = router;
