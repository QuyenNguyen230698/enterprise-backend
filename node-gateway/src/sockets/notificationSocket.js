// Maps portalUserId → Set of socket IDs (một user có thể mở nhiều tab)
const userSockets = new Map();

/**
 * Gửi notification real-time đến một user cụ thể.
 * Gọi từ bên ngoài (vd: sau khi tạo notification trong service).
 */
function emitToUser(io, portalUserId, event, payload) {
  const socketIds = userSockets.get(portalUserId);
  if (!socketIds) return;
  for (const socketId of socketIds) {
    io.to(socketId).emit(event, payload);
  }
}

/**
 * Gửi notification đến toàn bộ tenant (broadcast).
 * Room name: `tenant_{tenantId}`
 */
function emitToTenant(io, tenantId, event, payload) {
  io.to(`tenant_${tenantId}`).emit(event, payload);
}

module.exports = (io) => {
  // Namespace riêng cho notifications để tránh va chạm với meetingSocket
  const nsp = io.of("/notifications");

  nsp.on("connection", (socket) => {
    // ── notification:join ────────────────────────────────────────
    // Client gửi { portalUserId, tenantId } sau khi connect
    socket.on("notification:join", ({ portalUserId, tenantId } = {}) => {
      if (!portalUserId || !tenantId) return;

      socket.data.portalUserId = portalUserId;
      socket.data.tenantId = tenantId;

      // Join room theo tenant để broadcast
      socket.join(`tenant_${tenantId}`);

      // Lưu mapping user → socketIds
      if (!userSockets.has(portalUserId)) {
        userSockets.set(portalUserId, new Set());
      }
      userSockets.get(portalUserId).add(socket.id);

      console.log(`[Notification] ${portalUserId} joined (socket: ${socket.id})`);
    });

    // ── notification:join_admin ──────────────────────────────────
    // SuperAdmin join thêm room admin để nhận broadcast admin-wide
    socket.on("notification:join_admin", ({ tenantId } = {}) => {
      if (!tenantId) return;
      socket.join(`admin_${tenantId}`);
    });

    // ── notification:mark_read ───────────────────────────────────
    // Client emit để đồng bộ trạng thái đã đọc sang các tab khác
    socket.on("notification:mark_read", ({ notificationId } = {}) => {
      const { portalUserId } = socket.data;
      if (!portalUserId || !notificationId) return;

      const socketIds = userSockets.get(portalUserId);
      if (!socketIds) return;

      // Emit tới tất cả tab khác của cùng user (không gửi lại tab đang emit)
      for (const sid of socketIds) {
        if (sid !== socket.id) {
          nsp.to(sid).emit("notification:update", { notificationId, isRead: true });
        }
      }
    });

    // ── disconnect ───────────────────────────────────────────────
    socket.on("disconnect", () => {
      const { portalUserId } = socket.data;
      if (portalUserId) {
        const socketIds = userSockets.get(portalUserId);
        if (socketIds) {
          socketIds.delete(socket.id);
          if (socketIds.size === 0) userSockets.delete(portalUserId);
        }
      }
    });
  });

  // Export helper để các service khác có thể push notification
  module.exports.emitToUser = (portalUserId, event, payload) =>
    emitToUser(nsp, portalUserId, event, payload);
  module.exports.emitToTenant = (tenantId, event, payload) =>
    emitToTenant(nsp, tenantId, event, payload);
};
