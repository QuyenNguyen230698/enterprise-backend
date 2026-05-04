const proxyService = require("../services/proxy.service");

const emailConfigController = {
  // GET /email-config
  // Lấy danh sách tất cả cấu hình email của user hiện tại
  async list(req, res) {
    try {
      const data = await proxyService.listEmailConfigs(req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-config
  // Tạo cấu hình mới — payload gồm: name, provider, sender, isDefault, gmail? | smtp?
  // Credentials (appPassword / smtp.password) chỉ nhận khi tạo mới, không nhận khi update
  async create(req, res) {
    try {
      const { name, provider, sender, isDefault, gmail, smtp } = req.body;

      if (!name || !provider || !sender?.name || !sender?.email) {
        return res.status(422).json({ success: false, message: "Thiếu thông tin bắt buộc" });
      }
      if (!["gmail", "smtp"].includes(provider)) {
        return res.status(422).json({ success: false, message: "provider phải là gmail hoặc smtp" });
      }
      if (provider === "gmail" && !gmail?.appPassword) {
        return res.status(422).json({ success: false, message: "Gmail App Password là bắt buộc" });
      }
      if (provider === "smtp" && (!smtp?.host || !smtp?.port)) {
        return res.status(422).json({ success: false, message: "SMTP host và port là bắt buộc" });
      }

      const data = await proxyService.createEmailConfig(req.user.portal_user_id, req.body);
      res.status(201).json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // PUT /email-config/:id
  // Chỉ cho phép cập nhật: name, sender, isDefault
  // Credentials (password / appPassword) KHÔNG được cập nhật qua endpoint này
  async update(req, res) {
    try {
      const { name, sender, isDefault } = req.body;

      if (!name && !sender && isDefault === undefined) {
        return res.status(422).json({ success: false, message: "Không có field nào để cập nhật" });
      }

      const payload = {};
      if (name !== undefined) payload.name = name;
      if (sender !== undefined) payload.sender = sender;
      if (isDefault !== undefined) payload.isDefault = isDefault;

      const data = await proxyService.updateEmailConfig(req.params.id, req.user.portal_user_id, payload);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // DELETE /email-config/:id
  // Soft delete — đánh dấu is_active = false
  async remove(req, res) {
    try {
      const data = await proxyService.deleteEmailConfig(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-config/:id/set-default
  // Unset tất cả config khác → set config này là default
  async setDefault(req, res) {
    try {
      const data = await proxyService.setDefaultEmailConfig(req.params.id, req.user.portal_user_id);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-config/:id/test
  // Gửi email test đến địa chỉ người dùng nhập — body: { testEmail }
  async test(req, res) {
    try {
      const { testEmail } = req.body;
      if (!testEmail) {
        return res.status(422).json({ success: false, message: "testEmail là bắt buộc" });
      }

      const data = await proxyService.testEmailConfig(req.params.id, req.user.portal_user_id, { testEmail });
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /admin/system-email-config/send-template-test
  // Gửi HTML email test dùng email config default của user
  async sendTemplateTest(req, res) {
    try {
      const { to, subject, html } = req.body;
      if (!to || !html) {
        return res.status(422).json({ success: false, message: "to và html là bắt buộc" });
      }
      const data = await proxyService.sendTemplateTest(req.user.portal_user_id, { to, subject, html });
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /public/email/send-test (không cần auth)
  async publicSendTest(req, res) {
    try {
      const { to, subject, html, gmailEmail, gmailAppPassword } = req.body;
      if (!to || !html || !gmailEmail || !gmailAppPassword) {
        return res.status(422).json({ success: false, message: "to, html, gmailEmail và gmailAppPassword là bắt buộc" });
      }
      const data = await proxyService.publicSendTest({ to, subject, html, gmailEmail, gmailAppPassword });
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },

  // POST /email-config/validate-capacity
  // Kiểm tra capacity gửi email trước khi send campaign
  async validateCapacity(req, res) {
    try {
      const data = await proxyService.validateEmailCapacity(req.user.portal_user_id, req.body);
      res.json(data);
    } catch (e) {
      res.status(400).json({ success: false, message: e.message });
    }
  },
};

module.exports = emailConfigController;
