const { createClient } = require('redis');
require('dotenv').config();

const redisClient = createClient({
    url: process.env.REDIS_URL || 'redis://localhost:6379'
});

redisClient.on('error', (err) => console.error('Redis Client Error', err));
redisClient.on('connect', () => console.log('Redis Connected Successfully!'));

// Khởi động kết nối
(async () => {
    await redisClient.connect();
})();

module.exports = redisClient;