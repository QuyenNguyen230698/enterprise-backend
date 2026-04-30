const express = require("express");
const router = express.Router();
const proxyService = require("../services/proxy.service");
const { requireSuperAdmin } = require("../middleware/auth.middleware");

// ─── Permissions ──────────────────────────────────────────────────
// Mọi authenticated user đều cần endpoint này để build sidebar — không guard theo role
router.get("/permissions", async (req, res) => {
  try {
    const data = await proxyService.request("get", "/api/v1/roles/permissions");
    res.json(data);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

router.post("/permissions", requireSuperAdmin, async (req, res) => {
  try {
    const data = await proxyService.request("post", "/api/v1/roles/permissions", req.body);
    res.status(201).json(data);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

router.put("/permissions/:permission_id", requireSuperAdmin, async (req, res) => {
  try {
    const data = await proxyService.request("put", `/api/v1/roles/permissions/${req.params.permission_id}`, req.body);
    res.json(data);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

router.delete("/permissions/:permission_id", requireSuperAdmin, async (req, res) => {
  try {
    await proxyService.request("delete", `/api/v1/roles/permissions/${req.params.permission_id}`);
    res.status(204).send();
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

// ─── Roles ────────────────────────────────────────────────────────
router.get("/", requireSuperAdmin, async (req, res) => {
  try {
    const roles = await proxyService.request("get", "/api/v1/roles/");
    res.json(roles);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

router.post("/", requireSuperAdmin, async (req, res) => {
  try {
    const data = await proxyService.request("post", "/api/v1/roles/", req.body);
    res.status(201).json(data);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

router.get("/:role_id", requireSuperAdmin, async (req, res) => {
  try {
    const data = await proxyService.request("get", `/api/v1/roles/${req.params.role_id}`);
    res.json(data);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

router.put("/:role_id", requireSuperAdmin, async (req, res) => {
  try {
    const data = await proxyService.request("put", `/api/v1/roles/${req.params.role_id}`, req.body);
    res.json(data);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

router.delete("/:role_id", requireSuperAdmin, async (req, res) => {
  try {
    await proxyService.request("delete", `/api/v1/roles/${req.params.role_id}`);
    res.status(204).send();
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

module.exports = router;
