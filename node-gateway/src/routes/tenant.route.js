const express = require("express");
const router = express.Router();
const proxyService = require("../services/proxy.service");
const { requireSuperAdmin, requireAdmin } = require("../middleware/auth.middleware");

// GET / — chỉ superAdmin: trả toàn bộ tenants
router.get("/", requireSuperAdmin, async (req, res) => {
  try {
    const tenants = await proxyService.request("get", "/api/v1/tenants/");
    res.json(tenants);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

// GET /:tenantId — superAdmin hoặc admin (admin chỉ được lấy tenant của mình)
router.get("/:tenantId", requireAdmin, async (req, res) => {
  try {
    if (!req.isSuperAdmin && req.tenant_id !== req.params.tenantId) {
      return res.status(403).json({ error: "Admin chỉ được truy cập tenant của mình." });
    }
    const tenant = await proxyService.request("get", `/api/v1/tenants/${req.params.tenantId}`);
    res.json(tenant);
  } catch (e) {
    res.status(404).json({ error: e.message });
  }
});

// POST / — chỉ superAdmin: tạo tenant mới
router.post("/", requireSuperAdmin, async (req, res) => {
  try {
    const result = await proxyService.request("post", "/api/v1/tenants/", req.body);
    res.status(201).json(result);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

// PUT /:tenantId — chỉ superAdmin: cập nhật tenant
router.put("/:tenantId", requireSuperAdmin, async (req, res) => {
  try {
    const result = await proxyService.request("put", `/api/v1/tenants/${req.params.tenantId}`, req.body);
    res.json(result);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

// DELETE /:tenantId — chỉ superAdmin: xóa tenant
router.delete("/:tenantId", requireSuperAdmin, async (req, res) => {
  try {
    await proxyService.request("delete", `/api/v1/tenants/${req.params.tenantId}`);
    res.status(204).end();
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

// POST /:tenantId/assign-user — chỉ superAdmin
router.post("/:tenantId/assign-user/:portalUserId", requireSuperAdmin, async (req, res) => {
  try {
    const result = await proxyService.request(
      "post",
      `/api/v1/tenants/${req.params.tenantId}/assign-user/${req.params.portalUserId}`
    );
    res.json(result);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

module.exports = router;
