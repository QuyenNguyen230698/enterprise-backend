const redisClient = require('../config/redis');

const LOCK_TTL = 300; // Khóa trong 5 phút (300 giây) nếu user không submit

const lockService = {
    // Thử lấy quyền khóa mốc thời gian
    async acquireLock(roomId, timeSlot, userId) {
        const lockKey = `lock:room:${roomId}:time:${timeSlot}`;
        // NX: Chỉ set nếu key chưa tồn tại. EX: Thời gian sống
        const acquired = await redisClient.set(lockKey, userId, {
            NX: true,
            EX: LOCK_TTL
        });
        return acquired === 'OK'; // Trả về true nếu lấy được khóa
    },

    // Xóa khóa khi user đổi ý hoặc đã submit xong
    async releaseLock(roomId, timeSlot, userId) {
        const lockKey = `lock:room:${roomId}:time:${timeSlot}`;
        const currentOwner = await redisClient.get(lockKey);
        
        // Chỉ người giữ khóa mới được phép xóa
        if (currentOwner === userId) {
            await redisClient.del(lockKey);
            return true;
        }
        return false;
    }
};

module.exports = lockService;