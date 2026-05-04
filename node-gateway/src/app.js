require("dotenv").config();
const express = require("express");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");
const morgan = require("morgan");
const createError = require("http-errors");
const cors = require("cors");
const http = require("http");
const multer = require("multer");
const { createProxyMiddleware } = require("http-proxy-middleware");

const { Server } = require("socket.io");
const proxyService = require("./services/proxy.service");
const meetingSocket = require("./sockets/meetingSocket");
const notificationSocket = require("./sockets/notificationSocket");
const areaRoutes = require("./routes/area.route");
const roomRoutes = require("./routes/room.route");
const userRoutes = require("./routes/user.route");
const meetingRoutes = require("./routes/meeting.route");
const authRoutes = require("./routes/auth.route");
const tenantRoutes = require("./routes/tenant.route");
const roleRoutes = require("./routes/role.route");
const emailConfigRoutes = require("./routes/email-config.route");
const profileRoutes = require("./routes/profile.route");
const templateRoutes = require("./routes/template.route");
const emailListRoutes = require("./routes/email-list.route");
const campaignRoutes = require("./routes/campaign.route");
const notificationRoutes = require("./routes/notification.route");
const ticketRoutes = require("./routes/ticket.route");
const offboardingRoutes = require("./routes/offboarding.route");
const assetHandoverRoutes = require("./routes/asset-handover.route");
const jobHandoverRoutes = require("./routes/job-handover.route");
const exitInterviewRoutes = require("./routes/exit-interview.route");
const { authMiddleware } = require("./middleware/auth.middleware");

const app = express();
app.set("trust proxy", 1); // Tin tưởng Nginx proxy phía trước
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: "*" },
});

// 1. Bảo mật Header & CORS
app.use(
  helmet({
    crossOriginResourcePolicy: false,
    contentSecurityPolicy: false,
  }),
);
app.use(
  cors({
    origin: [
      "http://localhost:4995",
      "http://localhost:3000",
      "https://emtools.site",
      "https://www.emtools.site",
      "https://enterprise-meeting.pages.dev",
    ],
    methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"],
    credentials: true,
  }),
);

// -- PROXY SWAGGER TỪ PYTHON SANG CỔNG 5000 --
const PYTHON_URL = process.env.PYTHON_SERVICE_URL || "http://python-app:8000";

const swaggerProxy = createProxyMiddleware({
  target: PYTHON_URL,
  changeOrigin: true,
  pathRewrite: (path, req) => req.originalUrl,
});

app.use("/docs", swaggerProxy);
app.use("/openapi.json", swaggerProxy);
app.use("/static", swaggerProxy);

// 2. Sử dụng Multer & Express Parser
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
// Dùng multer để xử lý mọi trường hợp form-data (tránh lỗi rỗng body)
const upload = multer();
app.use(upload.any());

// 3. Log request đồng bộ console.log với màu sắc để thấy rõ status code
const colors = {
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  red: "\x1b[31m",
  reset: "\x1b[0m",
};

app.use(
  morgan((tokens, req, res) => {
    const status = tokens.status(req, res);
    const method = tokens.method(req, res);
    const url = tokens.url(req, res);
    const responseTime = tokens["response-time"](req, res);

    let color = colors.green;
    if (status >= 500) color = colors.red;
    else if (status >= 400) color = colors.yellow;

    return `${color}[GATEWAY] ${method} ${url} - Status: ${status} - ${responseTime}ms${colors.reset}`;
  }, {
    // Keep only error-like request logs.
    skip: (req, res) => Number(res.statusCode) < 400,
  }),
);

// Suppress browser favicon requests
app.get("/favicon.ico", (req, res) => res.status(204).end());

// API /check để kiểm tra gateway
app.get("/check", (req, res) => {
  res.status(200).json({
    status: "success",
    message: "🚀 API Gateway is running perfectly on port 8000!",
    timestamp: new Date().toISOString(),
  });
});

// 4. Giới hạn request
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 phút
  max: 2000,                 // 2000 request / 15 phút / IP (đủ cho admin panel + polling)
  standardHeaders: true,
  legacyHeaders: false,
  message: "Quá nhiều yêu cầu từ IP này, vui lòng thử lại sau.",
});

// Rate limit riêng cho auth (chặt hơn để bảo vệ login brute-force)
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 30,
  standardHeaders: true,
  legacyHeaders: false,
  message: "Quá nhiều lần thử đăng nhập, vui lòng thử lại sau 15 phút.",
});

app.use("/api/v1/auth", authLimiter);
app.use("/api/", limiter);

// ─── Routes ───────────────────────────────────────────────────────
app.use("/api/v1/auth", authRoutes);

// Public ticket contact — không cần auth (người dùng chưa đăng nhập)
const ticketController = require("./controllers/ticket.controller");
app.post("/api/v1/tickets/contact", ticketController.createContact);

// Internal service-to-service routes — verified by shared secret, no JWT needed
const internalSecret = process.env.INTERNAL_SECRET;
const internalAuth = (req, res, next) => {
  if (internalSecret && req.headers["x-internal-secret"] !== internalSecret) {
    return next(createError(403, "Forbidden: invalid internal secret."));
  }
  next();
};
const meetingController = require("./controllers/meeting.controller");
app.post(
  "/api/v1/meetings/internal/send-invite/:inviteId",
  internalAuth,
  meetingController.internalSendInvite,
);
app.post(
  "/api/v1/meetings/internal/cleanup-zoom-meetings",
  internalAuth,
  meetingController.internalCleanupZoom,
);

// Public invite response routes — no auth required (links sent via email)
app.get("/api/v1/meetings/invites/:inviteId/respond", meetingController.respondInviteGet);
app.put("/api/v1/meetings/invites/:inviteId/respond", meetingController.respondInvite);

// Protected entity routes
app.use("/api/v1/areas", authMiddleware, areaRoutes);
app.use("/api/v1/rooms", authMiddleware, roomRoutes);
app.use("/api/v1/users", authMiddleware, userRoutes);
app.use("/api/v1/meetings", authMiddleware, meetingRoutes);
app.use("/api/v1/tenants", authMiddleware, tenantRoutes);
app.use("/api/v1/roles",        authMiddleware, roleRoutes);
app.use("/api/v1/email-config", authMiddleware, emailConfigRoutes);
app.use("/api/v1/profile",      authMiddleware, profileRoutes);
app.use("/api/v1/templates",    authMiddleware, templateRoutes);
app.use("/api/v1/email-lists",  authMiddleware, emailListRoutes);
app.use("/api/v1/campaigns",      authMiddleware, campaignRoutes);
app.use("/api/v1/notifications",  authMiddleware, notificationRoutes);
app.use("/api/v1/tickets",        authMiddleware, ticketRoutes);
app.use("/api/v1/offboarding",    authMiddleware, offboardingRoutes);
app.use("/api/v1/asset-handover", authMiddleware, assetHandoverRoutes);
app.use("/api/v1/job-handover", authMiddleware, jobHandoverRoutes);
app.use("/api/v1/exit-interview", authMiddleware, exitInterviewRoutes);

// Send template test email using user's default email config
const emailConfigController = require("./controllers/email-config.controller");
app.post("/api/v1/admin/system-email-config/send-template-test", authMiddleware, emailConfigController.sendTemplateTest);

// Public: send test email using caller-supplied Gmail credentials (no auth required)
app.post("/api/v1/public/email/send-test", emailConfigController.publicSendTest);

// Kích hoạt Real-time Socket
meetingSocket(io);
notificationSocket(io);

// 5. Xử lý lỗi 404 (Không tìm thấy trang)
app.use((req, res, next) => {
  next(createError(404, "Endpoint không tồn tại"));
});

// 6. Global Error Handler (CHỐNG CRASH SEVER)
app.use((err, req, res, next) => {
  console.error("[CRITICAL ERROR]:", err.stack);
  res.status(err.status || 500).json({
    status: "error",
    message: err.message || "Lỗi server nội bộ",
  });
});

const PORT = process.env.PORT || 8000;
server.listen(PORT, () => {
  console.log(`🚀 Gateway đang chạy đồng bộ tại cổng ${PORT}`);
  console.log(`📘 Swagger Document tại: http://localhost:${PORT}/docs`);
});
