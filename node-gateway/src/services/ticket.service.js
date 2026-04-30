/**
 * ticket.service.js
 *
 * PostgreSQL (qua Python service) = source of truth cho tất cả ticket data.
 * Redis chỉ làm 2 việc:
 *   1. Distributed lock (SET NX EX 10) — ngăn 2 admin claim cùng lúc
 *   2. Pub/Sub — broadcast comment mới xuống SSE clients
 *
 * ── Phân quyền ────────────────────────────────────────────────────────────────
 *  superAdmin  Xem tất cả, claim tất cả, unlock/lock ticket, xử lý guest tickets
 *  admin       Xem ticket mình + member cùng tenant; claim ticket member cùng tenant
 *  member      Xem ticket của mình; tạo ticket; phản hồi
 *  guest       Gửi từ /contact (không đăng nhập); tạo ra Guest_T{random}
 * ──────────────────────────────────────────────────────────────────────────────
 */

const axios       = require('axios');
const redisClient = require('../config/redis');

const PYTHON_URL  = process.env.PYTHON_SERVICE_URL || 'http://python-app:8000';
const BASE        = `${PYTHON_URL}/api/v1/internal/tickets`;

const ROLE_SUPER  = '2000000001';
const ROLE_ADMIN  = '2000000002';
const ROLE_MEMBER = '2000000003';
const GUEST_TENANT = '__guest__';

// ─── Redis helpers ─────────────────────────────────────────────────────────────

const claimLockKey  = (ticketId) => `ticket:claim_lock:${ticketId}`;
const commentChannel = (ticketId) => `ticket:comments:${ticketId}`;

async function acquireClaimLock(ticketId, userId) {
  // SET key value NX EX 10 — atomic, chỉ set nếu chưa có key
  const result = await redisClient.set(
    claimLockKey(ticketId), userId, { NX: true, EX: 10 }
  );
  return result === 'OK';
}

async function releaseClaimLock(ticketId) {
  await redisClient.del(claimLockKey(ticketId));
}

// ─── Permission helpers ────────────────────────────────────────────────────────

function canViewTicket(ticket, requester) {
  if (!requester) return false;
  if (requester.role_id === ROLE_SUPER) return true;
  const uid = requester.portal_user_id || requester._id || requester.id;
  if (requester.role_id === ROLE_ADMIN) {
    if (ticket.userId === uid) return true;
    if (ticket.tenantId === requester.tenant_id && ticket.createdByRole === ROLE_MEMBER) return true;
    return false;
  }
  return ticket.userId === uid;
}

// Kiểm tra có thể thao tác quản lý (status/priority/resolve/close)
// Yêu cầu: đã claim (assignedTo === uid) HOẶC superAdmin
function canManageTicket(ticket, requester) {
  if (!requester) return false;
  if (requester.role_id === ROLE_SUPER) return true;
  if (ticket.isLocked) return false;
  const uid = requester.portal_user_id || requester._id || requester.id;
  if (requester.role_id === ROLE_ADMIN) {
    return ticket.assignedTo === uid &&
           ticket.tenantId === requester.tenant_id &&
           ticket.createdByRole === ROLE_MEMBER;
  }
  return false;
}

// Kiểm tra có thể claim ticket không
function canClaimTicket(ticket, requester) {
  if (!requester) return false;
  if (ticket.status === 'closed') return false;
  if (ticket.isLocked) return requester.role_id === ROLE_SUPER;
  if (requester.role_id === ROLE_SUPER) return true;
  const uid = requester.portal_user_id || requester._id || requester.id;
  if (requester.role_id === ROLE_ADMIN) {
    // admin chỉ claim ticket member cùng tenant chưa có ai nhận
    return (!ticket.assignedTo || ticket.assignedTo === uid) &&
           ticket.tenantId === requester.tenant_id &&
           ticket.createdByRole === ROLE_MEMBER;
  }
  return false;
}

// ─── HTTP helper ───────────────────────────────────────────────────────────────

async function pyFetch(method, path, body) {
  try {
    const res = await axios({
      method,
      url:     `${BASE}${path}`,
      data:    body,
      headers: { 'Content-Type': 'application/json' },
      validateStatus: () => true,  // handle all status codes manually
    });
    if (res.status >= 400) {
      const d = res.data || {};
      return {
        success: false,
        message: d.detail || d.message || `HTTP ${res.status}`,
        status:  res.status,
      };
    }
    return res.data;
  } catch (e) {
    return { success: false, message: e.message || 'Python service unreachable', status: 503 };
  }
}

// ─── Service ───────────────────────────────────────────────────────────────────

const ticketService = {

  // ── Tạo ticket ─────────────────────────────────────────────────────────────
  async createTicket(tenantId, user, payload) {
    return pyFetch('POST', '', {
      tenant_id:          tenantId,
      user_id:            user.portal_user_id || user.id,
      user_email:         user.email || '',
      user_name:          user.name || user.displayName || '',
      created_by_role:    user.role_id || ROLE_MEMBER,
      source:             payload.source || 'direct',
      subject:            payload.subject || '',
      description:        payload.description || '',
      category:           payload.category || 'other',
      priority:           payload.priority || 'medium',
      contact_email:      payload.contactEmail || '',
      email_notification: payload.emailNotification || false,
      attachments:        payload.attachments || [],
      status:             payload.status || 'open',
    });
  },

  // ── Tạo contact ticket (guest, không đăng nhập) ────────────────────────────
  async createContactTicket(payload) {
    return pyFetch('POST', '', {
      tenant_id:          GUEST_TENANT,
      user_id:            null,
      user_email:         payload.contactEmail || '',
      user_name:          payload.guestName || '',
      guest_display_name: payload.guestDisplayName || null,
      created_by_role:    'guest',
      source:             'contact_form',
      subject:            payload.subject || '',
      description:        payload.description || '',
      category:           payload.category || 'other',
      priority:           payload.priority || 'medium',
      contact_email:      payload.contactEmail || '',
      email_notification: !!payload.contactEmail,
      attachments:        [],
    });
  },

  // ── Lấy danh sách ticket cho admin-panel ──────────────────────────────────
  async getAllTickets(tenantId, requester, opts = {}) {
    const { page = 1, limit = 12, sort = '-created_at', status, category, priority, search } = opts;
    const uid = requester.portal_user_id || requester.id;

    const params = new URLSearchParams({ page, limit, sort });
    if (status && status !== 'all') params.set('status', status);
    if (category)  params.set('category', category);
    if (priority)  params.set('priority', priority);
    if (search)    params.set('search', search);

    if (requester.role_id === ROLE_SUPER) {
      params.set('all_tenants', 'true');
    } else {
      params.set('tenant_id', tenantId);
      params.set('user_id', uid);
      params.set('role', requester.role_id);
    }

    return pyFetch('GET', `?${params}`);
  },

  // ── Stats cho admin-panel ──────────────────────────────────────────────────
  async getStats(tenantId, requester) {
    const uid = requester.portal_user_id || requester.id;
    const params = new URLSearchParams();

    if (requester.role_id === ROLE_SUPER) {
      params.set('all_tenants', 'true');
    } else {
      params.set('tenant_id', tenantId);
      params.set('user_id', uid);
      params.set('role', requester.role_id);
    }

    return pyFetch('GET', `/stats?${params}`);
  },

  // ── Ticket của chính mình ─────────────────────────────────────────────────
  async getMyTickets(tenantId, requester, opts = {}) {
    const { page = 1, limit = 12, sort = '-created_at', status, search } = opts;
    const uid = requester.portal_user_id || requester.id;
    const params = new URLSearchParams({ page, limit, sort, tenant_id: tenantId, user_id: uid, role: ROLE_MEMBER });
    if (status && status !== 'all') params.set('status', status);
    if (search) params.set('search', search);
    return pyFetch('GET', `?${params}`);
  },

  // ── Stats ticket của chính mình ────────────────────────────────────────────
  async getMyStats(tenantId, requester) {
    const uid = requester.portal_user_id || requester.id;
    const params = new URLSearchParams({ tenant_id: tenantId, user_id: uid, role: ROLE_MEMBER });
    return pyFetch('GET', `/stats?${params}`);
  },

  // ── Chi tiết ticket ────────────────────────────────────────────────────────
  async getTicket(ticketId, requester) {
    const res = await pyFetch('GET', `/${ticketId}`);
    if (!res.success) return res;
    if (!canViewTicket(res.data, requester)) {
      return { success: false, message: 'Không có quyền xem ticket này', status: 403 };
    }
    return res;
  },

  // ── Claim ticket ───────────────────────────────────────────────────────────
  async claimTicket(ticketId, requester) {
    // Bước 1: kiểm tra ticket
    const ticketRes = await pyFetch('GET', `/${ticketId}`);
    if (!ticketRes.success) return ticketRes;
    const ticket = ticketRes.data;

    if (!canClaimTicket(ticket, requester)) {
      if (ticket.isLocked) return { success: false, message: 'Ticket đang bị khóa, chỉ superAdmin mới can thiệp', status: 423 };
      if (ticket.assignedTo && ticket.assignedTo !== (requester.portal_user_id || requester.id)) {
        return { success: false, message: `Ticket đã được ${ticket.assignedToName} nhận xử lý`, status: 409 };
      }
      return { success: false, message: 'Không có quyền nhận xử lý ticket này', status: 403 };
    }

    const uid  = requester.portal_user_id || requester.id;
    const name = requester.name || requester.displayName || '';

    // Bước 2: Redis lock 10s để tránh race condition giữa 2 admin cùng claim
    const gotLock = await acquireClaimLock(ticketId, uid);
    if (!gotLock) {
      return { success: false, message: 'Thao tác đang được xử lý, vui lòng thử lại', status: 429 };
    }

    try {
      // Bước 3: ghi vào PostgreSQL
      const res = await pyFetch('PUT', `/${ticketId}/claim`, { user_id: uid, user_name: name });
      return res;
    } finally {
      await releaseClaimLock(ticketId);
    }
  },

  // ── Unlock ticket (superAdmin) ─────────────────────────────────────────────
  async unlockTicket(ticketId, clearAssigned = true) {
    return pyFetch('PUT', `/${ticketId}/unlock`, { clear_assigned: clearAssigned });
  },

  // ── Lock ticket (superAdmin) ───────────────────────────────────────────────
  async lockTicket(ticketId) {
    return pyFetch('PUT', `/${ticketId}/lock`);
  },

  // ── Cập nhật status ────────────────────────────────────────────────────────
  async updateStatus(ticketId, status, resolution, requester) {
    const ticketRes = await pyFetch('GET', `/${ticketId}`);
    if (!ticketRes.success) return ticketRes;
    if (!canManageTicket(ticketRes.data, requester)) {
      return { success: false, message: 'Không có quyền cập nhật ticket này', status: 403 };
    }
    const uid  = requester.portal_user_id || requester.id;
    const name = requester.name || requester.displayName || '';
    const body = { status };
    if (resolution !== undefined) body.resolution = resolution;
    if (['resolved'].includes(status)) body.resolved_by = { userId: uid, userName: name, role_id: requester.role_id };
    return pyFetch('PUT', `/${ticketId}/status`, body);
  },

  // ── Cập nhật priority ──────────────────────────────────────────────────────
  async updatePriority(ticketId, priority, requester) {
    const ticketRes = await pyFetch('GET', `/${ticketId}`);
    if (!ticketRes.success) return ticketRes;
    if (!canManageTicket(ticketRes.data, requester)) {
      return { success: false, message: 'Không có quyền cập nhật ticket này', status: 403 };
    }
    return pyFetch('PUT', `/${ticketId}/priority`, { priority });
  },

  // ── Đóng ticket ────────────────────────────────────────────────────────────
  async closeTicket(ticketId, requester) {
    return ticketService.updateStatus(ticketId, 'closed', undefined, requester);
  },

  // ── Resolve ticket ─────────────────────────────────────────────────────────
  async resolveTicket(ticketId, resolution, resolvedBy) {
    return ticketService.updateStatus(ticketId, 'resolved', resolution, resolvedBy);
  },

  // ── Lưu resolution text ────────────────────────────────────────────────────
  async saveResolution(ticketId, resolution, requester) {
    const ticketRes = await pyFetch('GET', `/${ticketId}`);
    if (!ticketRes.success) return ticketRes;
    if (!canManageTicket(ticketRes.data, requester)) {
      return { success: false, message: 'Không có quyền cập nhật ticket này', status: 403 };
    }
    const uid  = requester.portal_user_id || requester.id;
    const name = requester.name || requester.displayName || '';
    return pyFetch('PUT', `/${ticketId}/resolution`, {
      resolution,
      resolved_by: { userId: uid, userName: name, role_id: requester.role_id },
    });
  },

  // ── Thêm comment + pub/sub ─────────────────────────────────────────────────
  async addComment(ticketId, user, payload) {
    const ticketRes = await pyFetch('GET', `/${ticketId}`);
    if (!ticketRes.success) return ticketRes;
    if (!canViewTicket(ticketRes.data, user)) {
      return { success: false, message: 'Không có quyền comment trên ticket này', status: 403 };
    }
    if (ticketRes.data.status === 'closed') {
      return { success: false, message: 'Ticket đã đóng', status: 400 };
    }

    const isAdmin      = user.role_id === ROLE_SUPER || user.role_id === ROLE_ADMIN;
    const isSuperAdmin = user.role_id === ROLE_SUPER;
    const uid          = user.portal_user_id || user.id;
    const name         = user.name || user.displayName || '';

    const res = await pyFetch('POST', `/${ticketId}/comments`, {
      user_id:        uid,
      user_name:      name,
      is_admin:       isAdmin,
      is_super_admin: isSuperAdmin,
      message:        payload.message || '',
      attachments:    payload.attachments || [],
    });

    if (res.success) {
      // Publish để SSE clients nhận real-time
      try {
        await redisClient.publish(
          commentChannel(ticketId),
          JSON.stringify({ ...res.data, ticketId }),
        );
      } catch (_) { /* non-fatal */ }
    }

    return res;
  },

  // ── Xóa comment ────────────────────────────────────────────────────────────
  async deleteComment(ticketId, commentId, user) {
    const ticketRes = await pyFetch('GET', `/${ticketId}`);
    if (!ticketRes.success) return ticketRes;
    if (!canViewTicket(ticketRes.data, user)) {
      return { success: false, message: 'Không có quyền trên ticket này', status: 403 };
    }

    // Kiểm tra comment thuộc về user hoặc superAdmin
    const comment = (ticketRes.data.comments || []).find((c) => String(c.id) === String(commentId));
    if (!comment) return { success: false, message: 'Comment không tồn tại', status: 404 };
    const uid = user.portal_user_id || user.id;
    if (user.role_id !== ROLE_SUPER && String(comment.userId) !== String(uid)) {
      return { success: false, message: 'Không có quyền xoá comment này', status: 403 };
    }

    return pyFetch('DELETE', `/${ticketId}/comments/${commentId}`);
  },

  // ── Contact tickets (superAdmin) ───────────────────────────────────────────
  async getContactTickets(opts = {}) {
    const { page = 1, limit = 12, sort = '-created_at', status, category, priority, search } = opts;
    const params = new URLSearchParams({ page, limit, sort, contact_only: 'true' });
    if (status && status !== 'all') params.set('status', status);
    if (category)  params.set('category', category);
    if (priority)  params.set('priority', priority);
    if (search)    params.set('search', search);
    return pyFetch('GET', `?${params}`);
  },

  async getContactStats() {
    return pyFetch('GET', '/stats?contact_only=true');
  },

  async getContactTicket(ticketId) {
    return pyFetch('GET', `/${ticketId}`);
  },

  async addContactComment(ticketId, user, payload) {
    return ticketService.addComment(ticketId, user, payload);
  },

  // ── Subscribe SSE (trả về async generator) ────────────────────────────────
  async *subscribeComments(ticketId) {
    const channel = commentChannel(ticketId);
    // Dùng duplicate connection để subscribe mà không block main client
    const sub = redisClient.duplicate();
    await sub.connect();
    const queue = [];
    let resolve;
    sub.subscribe(channel, (message) => {
      if (resolve) {
        const r = resolve;
        resolve = null;
        r(message);
      } else {
        queue.push(message);
      }
    });

    try {
      while (true) {
        if (queue.length > 0) {
          yield queue.shift();
        } else {
          yield await new Promise((r) => { resolve = r; });
        }
      }
    } finally {
      await sub.unsubscribe(channel);
      await sub.quit();
    }
  },
};

module.exports = ticketService;
module.exports.canViewTicket    = canViewTicket;
module.exports.canManageTicket  = canManageTicket;
module.exports.canClaimTicket   = canClaimTicket;
module.exports.GUEST_TENANT     = GUEST_TENANT;
