const jwt = require("jsonwebtoken");
const createError = require("http-errors");

const ROLE_SUPER_ADMIN = "2000000001";
const ROLE_ADMIN       = "2000000002";
const ROLE_MEMBER      = "2000000003";

const authMiddleware = (req, res, next) => {
  // SSE connections pass token via query param ?token=... (EventSource không hỗ trợ header)
  let token = req.query.token || null;
  if (!token) {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return next(createError(401, "No token provided. Please log in first."));
    }
    token = authHeader.split(" ")[1];
  }
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    req.user           = decoded;
    req.tenant_id      = decoded.tenant_id;
    req.role_id        = decoded.role_id;
    req.permission_ids = decoded.permission_ids || [];
    req.permissions    = decoded.permissions || {};
    req.isSuperAdmin   = decoded.role_id === ROLE_SUPER_ADMIN;
    req.isAdmin        = decoded.role_id === ROLE_ADMIN;
    req.isMember       = decoded.role_id === ROLE_MEMBER;
    next();
  } catch (error) {
    console.error("[AUTH MIDDLEWARE ERROR]:", error.message);
    return next(createError(401, "Invalid or expired token."));
  }
};

// Kiểm tra permission theo tên app — superAdmin bypass hoàn toàn
const requirePermission = (permissionName) => (req, res, next) => {
  if (req.isSuperAdmin) return next();
  const perms = req.permissions || {};
  const key = Object.keys(perms).find(k => k.toLowerCase() === permissionName.toLowerCase());
  if (key && perms[key]?.includes("view")) return next();
  return next(createError(403, `Bạn không có quyền truy cập '${permissionName}'.`));
};

// Chỉ cho phép superAdmin
const requireSuperAdmin = (req, res, next) => {
  if (req.isSuperAdmin) return next();
  return next(createError(403, "Chỉ superAdmin mới có quyền thực hiện thao tác này."));
};

// Chỉ cho phép superAdmin hoặc admin (không cho member)
const requireAdmin = (req, res, next) => {
  if (req.isSuperAdmin || req.isAdmin) return next();
  return next(createError(403, "Yêu cầu quyền admin trở lên."));
};

module.exports = {
  authMiddleware,
  requirePermission,
  requireSuperAdmin,
  requireAdmin,
  ROLE_SUPER_ADMIN,
  ROLE_ADMIN,
  ROLE_MEMBER,
};
