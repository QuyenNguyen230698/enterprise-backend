const ticketService = require('../services/ticket.service');

const ticketController = {

  // ── GET /tickets — admin-panel list ────────────────────────────────────────
  async list(req, res) {
    try {
      const { page = 1, limit = 12, sort = '-created_at', status, category, priority, search } = req.query;
      const result = await ticketService.getAllTickets(req.tenant_id, req.user, {
        page: parseInt(page), limit: parseInt(limit), sort, status, category, priority, search,
      });
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── GET /tickets/stats ─────────────────────────────────────────────────────
  async stats(req, res) {
    try {
      res.json(await ticketService.getStats(req.tenant_id, req.user));
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── GET /tickets/my-tickets ────────────────────────────────────────────────
  async myTickets(req, res) {
    try {
      const { page = 1, limit = 12, sort = '-created_at', status, search } = req.query;
      const result = await ticketService.getMyTickets(req.tenant_id, req.user, {
        page: parseInt(page), limit: parseInt(limit), sort, status, search,
      });
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── GET /tickets/my-stats ──────────────────────────────────────────────────
  async myStats(req, res) {
    try {
      res.json(await ticketService.getMyStats(req.tenant_id, req.user));
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── GET /tickets/:id ───────────────────────────────────────────────────────
  async get(req, res) {
    try {
      const result = await ticketService.getTicket(req.params.id, req.user);
      if (!result.success) return res.status(result.status || 404).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── POST /tickets ──────────────────────────────────────────────────────────
  async create(req, res) {
    try {
      const { subject, description } = req.body;
      if (!subject?.trim() || !description?.trim()) {
        return res.status(400).json({ success: false, message: 'subject và description là bắt buộc' });
      }
      const result = await ticketService.createTicket(req.tenant_id, req.user, req.body);
      res.status(result.success ? 201 : 400).json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── POST /tickets/contact (public, không cần auth) ────────────────────────
  async createContact(req, res) {
    try {
      const { subject, description } = req.body;
      if (!subject?.trim() || !description?.trim()) {
        return res.status(400).json({ success: false, message: 'subject và description là bắt buộc' });
      }
      const result = await ticketService.createContactTicket(req.body);
      res.status(result.success ? 201 : 400).json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── PUT /tickets/:id/claim ─────────────────────────────────────────────────
  async claim(req, res) {
    try {
      const result = await ticketService.claimTicket(req.params.id, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── PUT /tickets/:id/unlock (superAdmin) ───────────────────────────────────
  async unlock(req, res) {
    try {
      const clearAssigned = req.body.clear_assigned !== false;
      const result = await ticketService.unlockTicket(req.params.id, clearAssigned);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── PUT /tickets/:id/lock (superAdmin) ────────────────────────────────────
  async lock(req, res) {
    try {
      const result = await ticketService.lockTicket(req.params.id);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── PUT /tickets/:id/status ────────────────────────────────────────────────
  async updateStatus(req, res) {
    try {
      const { status, resolution } = req.body;
      if (!status) return res.status(400).json({ success: false, message: 'status là bắt buộc' });
      const result = await ticketService.updateStatus(req.params.id, status, resolution, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── PUT /tickets/:id/priority ──────────────────────────────────────────────
  async updatePriority(req, res) {
    try {
      const { priority } = req.body;
      if (!priority) return res.status(400).json({ success: false, message: 'priority là bắt buộc' });
      const result = await ticketService.updatePriority(req.params.id, priority, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── PUT /tickets/:id/resolve ───────────────────────────────────────────────
  async resolve(req, res) {
    try {
      const { resolution } = req.body;
      if (!resolution?.trim()) {
        return res.status(400).json({ success: false, message: 'resolution là bắt buộc' });
      }
      const result = await ticketService.resolveTicket(req.params.id, resolution, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── PUT /tickets/:id/resolution (lưu ghi chú giải pháp) ───────────────────
  async saveResolution(req, res) {
    try {
      const { resolution } = req.body;
      if (!resolution?.trim()) {
        return res.status(400).json({ success: false, message: 'resolution là bắt buộc' });
      }
      const result = await ticketService.saveResolution(req.params.id, resolution, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── PUT /tickets/:id/close ─────────────────────────────────────────────────
  async close(req, res) {
    try {
      const result = await ticketService.closeTicket(req.params.id, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── POST /tickets/:id/comments ─────────────────────────────────────────────
  async addComment(req, res) {
    try {
      const { message, attachments } = req.body;
      if (!message?.trim() && (!attachments || !attachments.length)) {
        return res.status(400).json({ success: false, message: 'message hoặc attachments là bắt buộc' });
      }
      const result = await ticketService.addComment(req.params.id, req.user, req.body);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── DELETE /tickets/:id/comments/:commentId ────────────────────────────────
  async deleteComment(req, res) {
    try {
      const result = await ticketService.deleteComment(req.params.id, req.params.commentId, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  // ── GET /tickets/:id/comments/stream — SSE real-time ──────────────────────
  async streamComments(req, res) {
    res.setHeader('Content-Type',       'text/event-stream');
    res.setHeader('Cache-Control',      'no-cache');
    res.setHeader('Connection',         'keep-alive');
    res.setHeader('X-Accel-Buffering',  'no');
    res.flushHeaders();

    const ticketId = req.params.id;
    const ticketRes = await ticketService.getTicket(ticketId, req.user).catch(() => null);
    if (!ticketRes?.success) {
      res.write(`event: error\ndata: ${JSON.stringify({ message: 'Không có quyền' })}\n\n`);
      return res.end();
    }

    res.write(': connected\n\n');
    const heartbeat = setInterval(() => {
      if (!res.writableEnded) res.write(': ping\n\n');
    }, 25000);

    try {
      for await (const message of ticketService.subscribeComments(ticketId)) {
        if (res.writableEnded) break;
        res.write(`event: comment\ndata: ${message}\n\n`);
      }
    } catch (_) {
      // client disconnected
    } finally {
      clearInterval(heartbeat);
      if (!res.writableEnded) res.end();
    }
  },

  // ── Contact tickets (superAdmin) ──────────────────────────────────────────
  async listContact(req, res) {
    try {
      const { page = 1, limit = 12, sort = '-created_at', status, category, priority, search } = req.query;
      const result = await ticketService.getContactTickets({
        page: parseInt(page), limit: parseInt(limit), sort, status, category, priority, search,
      });
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  async contactStats(req, res) {
    try {
      res.json(await ticketService.getContactStats());
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  async getContactTicket(req, res) {
    try {
      const result = await ticketService.getContactTicket(req.params.id);
      if (!result.success) return res.status(result.status || 404).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  async addContactComment(req, res) {
    try {
      const { message, attachments } = req.body;
      if (!message?.trim() && (!attachments || !attachments.length)) {
        return res.status(400).json({ success: false, message: 'message hoặc attachments là bắt buộc' });
      }
      const result = await ticketService.addContactComment(req.params.id, req.user, req.body);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  async updateContactStatus(req, res) {
    try {
      const { status, resolution } = req.body;
      if (!status) return res.status(400).json({ success: false, message: 'status là bắt buộc' });
      const result = await ticketService.updateStatus(req.params.id, status, resolution, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },

  async resolveContact(req, res) {
    try {
      const { resolution } = req.body;
      if (!resolution?.trim()) {
        return res.status(400).json({ success: false, message: 'resolution là bắt buộc' });
      }
      const result = await ticketService.resolveTicket(req.params.id, resolution, req.user);
      if (!result.success) return res.status(result.status || 400).json(result);
      res.json(result);
    } catch (e) { res.status(500).json({ success: false, message: e.message }); }
  },
};

module.exports = ticketController;
