const proxyService = require("../services/proxy.service");

const meetingController = {
  async list(req, res) {
    try {
      // Inject portal_user_id từ JWT — frontend không cần gửi
      const query = { ...req.query, portal_user_id: req.user.portal_user_id };
      const meetings = await proxyService.listMeetings(query);
      res.json(meetings);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async create(req, res) {
    try {
      // Inject organizer_id và created_by từ JWT — không tin frontend
      const body = {
        ...req.body,
        organizer_id: req.user.portal_user_id,
        created_by: req.user.portal_user_id,
      };
      const meeting = await proxyService.createMeeting(body);
      res.status(201).json(meeting);
    } catch (e) {
      // 409 Conflict for conflicting meeting
      const status =
        e.message.includes("conflict") || e.message.includes("already booked")
          ? 409
          : 400;
      res.status(status).json({ error: e.message });
    }
  },

  async getById(req, res) {
    try {
      const meeting = await proxyService.getMeeting(req.params.id);
      res.json(meeting);
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  },

  async update(req, res) {
    try {
      const meeting = await proxyService.updateMeeting(req.params.id, req.body);
      res.json(meeting);
    } catch (e) {
      const status = e.message.includes("conflict") ? 409 : 400;
      res.status(status).json({ error: e.message });
    }
  },

  async remove(req, res) {
    try {
      await proxyService.deleteMeeting(req.params.id);
      res.status(204).send();
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async cancel(req, res) {
    try {
      const meeting = await proxyService.cancelMeeting(req.params.id);
      res.json(meeting);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  // ─── Invites ─────────────────────────────────────────────────
  async listInvites(req, res) {
    try {
      const invites = await proxyService.listInvites(req.params.id);
      res.json(invites);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async addInvite(req, res) {
    try {
      const invite = await proxyService.addInvite(req.params.id, req.body);
      res.status(201).json(invite);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async respondInvite(req, res) {
    try {
      const invite = await proxyService.respondInvite(
        req.params.inviteId,
        req.body,
      );
      res.json(invite);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },

  async respondInviteGet(req, res) {
    try {
      const html = await proxyService.respondInviteGet(
        req.params.inviteId,
        req.query,
      );
      res.send(html);
    } catch (e) {
      res.status(400).send(`<h1>Error</h1><p>${e.message}</p>`);
    }
  },

  async internalSendInvite(req, res) {
    try {
      const result = await proxyService.internalSendInvite(req.params.inviteId);
      res.json(result);
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  },
};

module.exports = meetingController;
