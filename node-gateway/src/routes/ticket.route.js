/**
 * Ticket routes
 *
 * PUBLIC (app.js, trước authMiddleware)
 *   POST  /api/v1/tickets/contact          → Mọi người (kể cả chưa đăng nhập)
 *
 * AUTH — mọi role
 *   GET   /my-tickets                      → Ticket của chính mình
 *   GET   /my-stats                        → Stats của chính mình
 *   POST  /                                → Tạo ticket
 *   GET   /:id                             → Chi tiết (service check canView)
 *   GET   /:id/comments/stream             → SSE real-time comments
 *   POST  /:id/comments                    → Comment (service check canView)
 *   DELETE /:id/comments/:commentId        → Xóa comment
 *
 * requireAdmin (admin + superAdmin)
 *   GET   /                                → Danh sách (scope theo role)
 *   GET   /stats                           → Stats (scope theo role)
 *   PUT   /:id/claim                       → Nhận xử lý (claim)
 *   PUT   /:id/status                      → Đổi trạng thái (chỉ assigned_to)
 *   PUT   /:id/priority                    → Đổi ưu tiên (chỉ assigned_to)
 *   PUT   /:id/resolve                     → Resolve (chỉ assigned_to)
 *   PUT   /:id/resolution                  → Lưu ghi chú giải pháp
 *   PUT   /:id/close                       → Đóng ticket (chỉ assigned_to)
 *
 * requireSuperAdmin
 *   PUT   /:id/unlock                      → Mở khóa + reset assigned_to
 *   PUT   /:id/lock                        → Khóa (chỉ superAdmin can thiệp)
 *   GET   /contact/stats
 *   GET   /contact
 *   GET   /contact/:id
 *   PUT   /contact/:id/resolve
 *   PUT   /contact/:id/status
 *   POST  /contact/:id/comments
 */

const express = require('express');
const router  = express.Router();
const c       = require('../controllers/ticket.controller');
const { requireSuperAdmin, requireAdmin } = require('../middleware/auth.middleware');

// ── SuperAdmin: contact tickets (trước /* để không bị nuốt bởi /:id) ─────────
router.get('/contact/stats',         requireSuperAdmin, c.contactStats);
router.get('/contact',               requireSuperAdmin, c.listContact);
router.get('/contact/:id',           requireSuperAdmin, c.getContactTicket);
router.put('/contact/:id/resolve',   requireSuperAdmin, c.resolveContact);
router.put('/contact/:id/status',    requireSuperAdmin, c.updateContactStatus);
router.post('/contact/:id/comments', requireSuperAdmin, c.addContactComment);

// ── Mọi role đã login ─────────────────────────────────────────────────────────
router.get('/my-tickets', c.myTickets);
router.get('/my-stats',   c.myStats);

// ── Admin + superAdmin ────────────────────────────────────────────────────────
router.get('/stats', requireAdmin, c.stats);
router.get('/',      requireAdmin, c.list);

// ── Mọi role — tạo ticket ─────────────────────────────────────────────────────
router.post('/', c.create);

// ── SSE stream — trước /:id để không bị match nhầm ───────────────────────────
router.get('/:id/comments/stream', c.streamComments);

// ── Chi tiết ticket ───────────────────────────────────────────────────────────
router.get('/:id', c.get);

// ── Claim — admin + superAdmin ────────────────────────────────────────────────
router.put('/:id/claim', requireAdmin, c.claim);

// ── SuperAdmin: lock/unlock ───────────────────────────────────────────────────
router.put('/:id/unlock', requireSuperAdmin, c.unlock);
router.put('/:id/lock',   requireSuperAdmin, c.lock);

// ── Admin + superAdmin — quản lý (service check canManageTicket) ──────────────
router.put('/:id/resolve',    requireAdmin, c.resolve);
router.put('/:id/resolution', requireAdmin, c.saveResolution);
router.put('/:id/status',     requireAdmin, c.updateStatus);
router.put('/:id/priority',   requireAdmin, c.updatePriority);
router.put('/:id/close',      requireAdmin, c.close);

// ── Comment — mọi role (service check canView) ────────────────────────────────
router.post('/:id/comments',              c.addComment);
router.delete('/:id/comments/:commentId', c.deleteComment);

module.exports = router;
