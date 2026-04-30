const lockService = require('../services/lock.service');

const activeDrafts = {}; // { socketId: { roomId, date, startTime, endTime, userId } }

module.exports = (io) => {
    io.on('connection', (socket) => {
        console.log(`User connected: ${socket.id}`);

        // Client begins drafting a schedule or updates their drafted times
        socket.on('draft_schedule', (draftData) => {
            // draftData: { roomId, date, startTime, endTime, userId }
            if (draftData && draftData.startTime && draftData.endTime && draftData.date) {
                activeDrafts[socket.id] = draftData;
            } else {
                delete activeDrafts[socket.id];
            }
            // Broadcast changes to everyone so they can update their disabled rooms
            io.emit('active_drafts_updated', Object.values(activeDrafts));
        });

        // Client signals that a booking was successfully saved to the database
        socket.on('booking_saved', () => {
            // Signal all other clients to refresh their data from the API
            socket.broadcast.emit('refresh_bookings');
            // Clear any lingering drafts from this socket since the booking is now permanent
            if (activeDrafts[socket.id]) {
                delete activeDrafts[socket.id];
                io.emit('active_drafts_updated', Object.values(activeDrafts));
            }
        });

        // Tự động nhả khóa nếu user tắt tab trình duyệt
        socket.on('disconnect', async () => {
            if (activeDrafts[socket.id]) {
                delete activeDrafts[socket.id];
                io.emit('active_drafts_updated', Object.values(activeDrafts));
            }
            console.log(`User disconnected: ${socket.id}`);
        });
    });
};