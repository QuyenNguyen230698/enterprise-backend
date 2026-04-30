const express = require('express');
const router = express.Router();
const c = require('../controllers/area.controller');
// Areas: mọi user đã login đều có thể thao tác
router.get('/',               c.list);
router.post('/',              c.create);
router.get('/:id',            c.getById);
router.put('/:id',            c.update);
router.delete('/:id',         c.remove);
router.get('/:id/rooms',      c.getRooms);
router.post('/shared-access', c.createSharedAccess);

module.exports = router;
