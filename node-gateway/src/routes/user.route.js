const express = require('express');
const router = express.Router();
const c = require('../controllers/user.controller');
const { requireSuperAdmin, requireAdmin } = require('../middleware/auth.middleware');

// /me và tenant-members: mọi user đã login đều dùng được (bookings cần tenant-members)
router.get('/me',             c.me);
router.get('/tenant-members', c.tenantMembers);

// Quản lý user: list/get dành cho admin+, tạo/sửa/xóa chỉ superAdmin
router.get('/',                 requireAdmin, c.list);
router.post('/',                requireSuperAdmin, c.upsert);
router.get('/portal/:portalId', requireAdmin, c.getByPortalId);
router.get('/:id',              requireAdmin, c.getById);
router.put('/:id',              requireAdmin, c.update);
router.delete('/:id',           requireSuperAdmin, c.remove);

module.exports = router;
