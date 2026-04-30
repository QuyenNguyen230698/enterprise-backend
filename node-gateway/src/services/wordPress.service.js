const axios = require('axios');
require('dotenv').config();

const WORDPRESS_URL = process.env.WORDPRESS_URL || 'https://gatewaycityvinhlong.vn/wp-json';

const wordPressService = {
    /**
     * Fetch all meeting data from WordPress
     * Assumes a custom endpoint or standard posts with custom fields
     */
    async fetchMeetingData() {
        try {
            const response = await axios.get(`${WORDPRESS_URL}/wp/v2/meetings`);
            return response.data;
        } catch (error) {
            console.error('Lỗi khi lấy dữ liệu từ WordPress:', error.message);
            throw new Error('Không thể đồng bộ dữ liệu từ WordPress.');
        }
    },

    /**
     * Sync a single meeting to WordPress (optional)
     */
    async syncMeeting(meetingData) {
        try {
            // Placeholder for syncing back to WP if needed
            // const response = await axios.post(`${WORDPRESS_URL}/wp/v2/meetings`, meetingData);
            // return response.data;
            return { success: true, message: 'Đã giả lập đồng bộ sang WordPress' };
        } catch (error) {
            console.error('Lỗi khi đồng bộ sang WordPress:', error.message);
            return { success: false, error: error.message };
        }
    }
};

module.exports = wordPressService;
