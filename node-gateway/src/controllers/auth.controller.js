const { OAuth2Client } = require("google-auth-library");
const jwt = require("jsonwebtoken");
const axios = require("axios");
const createError = require("http-errors");

const getOAuthClient = (redirectUri) => {
  return new OAuth2Client(
    process.env.GOOGLE_CLIENT_ID,
    process.env.GOOGLE_CLIENT_SECRET,
    redirectUri
  );
};

/**
 * Exchange Google Code for Token and Profile, then upsert user in Python Backend.
 * Role và permissions được đọc động từ bảng roles/permissions trong DB,
 * KHÔNG hardcode cứng trong code.
 */
exports.googleLogin = async (req, res, next) => {
  try {
    const { code, redirect_uri } = req.body;
    const client = getOAuthClient(redirect_uri || process.env.GOOGLE_REDIRECT_URI || "http://localhost:4995/callback");

    if (!code) {
      throw createError(400, "Google Auth Code is required.");
    }

    const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || "http://python-app:8000";

    // 1. Exchange code for tokens
    const { tokens } = await client.getToken(code);
    client.setCredentials(tokens);

    // 2. Get user info from Google
    const ticket = await client.verifyIdToken({
      idToken: tokens.id_token,
      audience: process.env.GOOGLE_CLIENT_ID,
    });
    const payload = ticket.getPayload();
    const { sub, email, name, picture } = payload;

    // 3. Resolve tenant_id by email domain
    const emailDomain = email.split("@")[1];
    let resolvedTenantId = null;
    try {
      const tenantRes = await axios.get(
        `${PYTHON_SERVICE_URL}/api/v1/tenants/by-domain?domain=${encodeURIComponent(emailDomain)}`
      );
      resolvedTenantId = tenantRes.data.tenant_id;
    } catch (_) {
      // No tenant matched — user gets personal space
    }

    // 4. Upsert user in Python Backend
    const upsertPayload = {
      email,
      name,
      full_name: name,
      avatar_url: picture,
      google_id: sub,
      google_token: tokens.access_token,
      // New SSO users must start as guest; admin flow can promote later.
      role: "2000000005",
    };
    if (resolvedTenantId) upsertPayload.tenant_id = resolvedTenantId;

    const upsertResponse = await axios.post(`${PYTHON_SERVICE_URL}/api/v1/users/`, upsertPayload);
    const upsertedUser = upsertResponse.data;

    // 5. Re-fetch user để lấy role_id hiện tại từ DB
    const userResponse = await axios.get(
      `${PYTHON_SERVICE_URL}/api/v1/users/portal/${upsertedUser.portal_user_id}`
    );
    const user = userResponse.data;

    // 6. Xác định role_id thực tế:
    //    tenant_admins có độ ưu tiên cao hơn users.role
    let roleId = user.role; // role_id từ bảng users (đã là 10 số)

    if (resolvedTenantId && user.portal_user_id) {
      try {
        const tenantRes = await axios.get(
          `${PYTHON_SERVICE_URL}/api/v1/tenants/${resolvedTenantId}`
        );
        const tenantAdmins = tenantRes.data?.admins || [];
        const adminEntry = tenantAdmins.find(
          (a) => a.portal_user_id === user.portal_user_id && a.is_active
        );
        if (adminEntry) {
          // Tenant admin: map is_super_admin → role_id tương ứng
          // superAdmin role_id = "2000000001", admin role_id = "2000000002"
          roleId = adminEntry.is_super_admin ? "2000000001" : "2000000002";
        }
      } catch (_) {
        // Keep roleId from user.role
      }
    }

    // 7. Query Role từ DB để lấy danh sách permission_id
    let roleData = null;
    let permissionNames = [];
    try {
      const roleRes = await axios.get(
        `${PYTHON_SERVICE_URL}/api/v1/roles/${roleId}`
      );
      roleData = roleRes.data;
      // roleData.permission_objects = [{permission_id, name, ...}]
      permissionNames = (roleData.permission_objects || []).map((p) => p.name);
    } catch (_) {
      // Fallback: nếu không tìm thấy role thì chỉ cho bookings
      permissionNames = ["bookings", "dashboard"];
    }

    // 8. Build permissions object (dạng {appCode: ['view','create',...]} cho backward compat)
    const fullAccess = ["view", "create", "update", "delete"];
    const permissions = {};
    permissionNames.forEach((name) => {
      permissions[name] = fullAccess;
    });
    // dashboard chỉ view
    if (permissions["dashboard"]) permissions["dashboard"] = ["view"];

    // 9. Sign JWT
    const internalToken = jwt.sign(
      {
        id: user.id,
        portal_user_id: user.portal_user_id,
        email: user.email,
        tenant_id: user.tenant_id,
        role_id: roleId,
        role_name: roleData?.name || "member",
        permission_ids: roleData?.permissions || [],
        permissions,
      },
      process.env.JWT_SECRET,
      { expiresIn: `${process.env.JWT_EXPIRATION_HOURS || 24}h` }
    );

    res.status(200).json({
      status: "success",
      data: {
        token: internalToken,
        user: {
          id: user.id,
          portal_user_id: user.portal_user_id,
          email: user.email,
          name: user.name,
          avatar_url: user.avatar_url,
          tenant_id: user.tenant_id,
          role_id: roleId,
          role_name: roleData?.name || "member",
          permission_ids: roleData?.permissions || [],
          permissions,
        },
      },
    });
  } catch (error) {
    console.error("[AUTH ERROR]:", error.response?.data || error.message);
    next(createError(500, "Authentication with Google failed."));
  }
};
