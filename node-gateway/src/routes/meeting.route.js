const express = require('express');
const router = express.Router();
const c = require('../controllers/meeting.controller');
const { requirePermission } = require('../middleware/auth.middleware');

// Meeting CRUD: cần permission "bookings"
router.get('/',                              requirePermission('bookings'), c.list);
router.post('/',                             requirePermission('bookings'), c.create);
router.get('/:id',                           requirePermission('bookings'), c.getById);
router.put('/:id',                           requirePermission('bookings'), c.update);
router.delete('/:id',                        requirePermission('bookings'), c.remove);
router.patch('/:id/cancel',                  requirePermission('bookings'), c.cancel);

// Meeting Invites: cần permission "bookings"
router.get('/:id/invites',                   requirePermission('bookings'), c.listInvites);
router.post('/:id/invites',                  requirePermission('bookings'), c.addInvite);

// Public invite response links (email link — không cần auth)
router.get('/invites/:inviteId/respond',     c.respondInviteGet);
router.put('/invites/:inviteId/respond',     c.respondInvite);

// Internal Email Trigger (worker — dùng shared secret, không qua authMiddleware)
router.post('/internal/send-invite/:inviteId', c.internalSendInvite);

module.exports = router;
