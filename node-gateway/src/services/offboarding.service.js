/**
 * offboarding.service.js
 *
 * PostgreSQL (qua Python service) = source of truth cho tất cả offboarding data.
 * Redis đã được loại bỏ hoàn toàn.
 */

const axios = require("axios");

const PYTHON_URL = process.env.PYTHON_SERVICE_URL || "http://python-app:8000";
const BASE = `${PYTHON_URL}/api/v1/internal/offboarding`;

const ROLE_SUPER = "2000000001";
const ROLE_ADMIN = "2000000002";
const RESTRICTED_SUBMIT_KEYWORDS = ["GM", "DIRECTOR", "MANAGER", "LEADER", "CHIEF"];

function getUserId(reqUser) {
  const id = reqUser?.portal_user_id || reqUser?.id || null;
  return id != null ? String(id) : null;
}

function isProcessEmployee(reqUser, process) {
  const processIds = [
    process?.employee_id,
    process?.employee_code,
  ]
    .map((v) => String(v || "").trim())
    .filter(Boolean);

  const actorIds = [
    reqUser?.portal_user_id,
    reqUser?.id,
    reqUser?.employee_id,
    reqUser?.employee_code,
    reqUser?.e_code,
    reqUser?.hr_code,
  ]
    .map((v) => String(v || "").trim())
    .filter(Boolean);

  return actorIds.some((id) => processIds.includes(id));
}

function getUserName(reqUser) {
  return reqUser?.full_name || reqUser?.name || reqUser?.display_name || "Unknown";
}

function isAdminLike(reqUser) {
  return [ROLE_SUPER, ROLE_ADMIN].includes(reqUser?.role_id);
}

function isSuper(reqUser) {
  return reqUser?.role_id === ROLE_SUPER;
}

function normalizeUpper(value) {
  return String(value || "").trim().toUpperCase();
}

function resolveActorContext(reqUser, actorProfile) {
  return {
    deptCode: normalizeUpper(
      reqUser?.dept_code ||
      reqUser?.deptCode ||
      actorProfile?.dept_code ||
      actorProfile?.department ||
      ""
    ),
    department: normalizeUpper(
      reqUser?.department ||
      reqUser?.dept ||
      actorProfile?.department ||
      ""
    ),
    title: normalizeUpper(
      reqUser?.title ||
      actorProfile?.title ||
      ""
    ),
  };
}

function departmentFromDeptCode(deptCode) {
  const code = normalizeUpper(deptCode);
  if (!code) return "";
  return code.split("_")[0] || code;
}

function canSubmitByDeptCode(deptCode) {
  const code = normalizeUpper(deptCode);
  if (!code) return false;
  return !RESTRICTED_SUBMIT_KEYWORDS.some((kw) => code.includes(kw));
}

function isManagerOrDirectorDeptApprover(actorDeptCode, actorTitle, employeeDeptCode) {
  const actorCode = normalizeUpper(actorDeptCode);
  const title = normalizeUpper(actorTitle);
  const actorDeptRoot = departmentFromDeptCode(actorCode);
  const employeeDeptRoot = departmentFromDeptCode(employeeDeptCode);
  if (!actorDeptRoot || !employeeDeptRoot) return false;
  const sameDept = actorDeptRoot === employeeDeptRoot;
  const isManagerLevel =
    actorCode.includes("MANAGER") ||
    actorCode.includes("DIRECTOR") ||
    title.includes("MANAGER") ||
    title.includes("DIRECTOR") ||
    title.includes("TRƯỞNG PHÒNG") ||
    title.includes("GIÁM ĐỐC");
  return sameDept && isManagerLevel;
}

function isHRStaff(actorDeptCode) {
  const actorCode = normalizeUpper(actorDeptCode);
  return departmentFromDeptCode(actorCode) === "HR" && actorCode.includes("HR_STAFF");
}

function isHRManagerOrDirector(actorDeptCode) {
  const actorCode = normalizeUpper(actorDeptCode);
  const sameDept = departmentFromDeptCode(actorCode) === "HR";
  const allowed = actorCode.includes("HR_MANAGER") || actorCode.includes("HR_DIRECTOR");
  return sameDept && allowed;
}

function isGMApprover(actorDeptCode) {
  const actorCode = normalizeUpper(actorDeptCode);
  return actorCode === "GM" || actorCode.includes("GM_DIRECTOR");
}

function canTakeWorkflowStepAction(actorDeptCode, actorTitle, processDeptCode, stepNumber) {
  if (stepNumber === 2) return isManagerOrDirectorDeptApprover(actorDeptCode, actorTitle, processDeptCode);
  if (stepNumber === 3) return isHRStaff(actorDeptCode);
  if (stepNumber === 4) return isHRManagerOrDirector(actorDeptCode);
  if (stepNumber === 5) return isGMApprover(actorDeptCode);
  if (stepNumber === 7) return isGMApprover(actorDeptCode);
  return false;
}

function canTakeHandoverAction(actorDeptCode, actorTitle, processDeptCode, hoKey) {
  if (hoKey === "ho1") return isManagerOrDirectorDeptApprover(actorDeptCode, actorTitle, processDeptCode);
  if (hoKey === "ho2" || hoKey === "ho3") return isHRStaff(actorDeptCode) || isHRManagerOrDirector(actorDeptCode);
  return false;
}

async function hasUserSignature(reqUser) {
  const portalUserId = getUserId(reqUser);
  if (!portalUserId) return false;
  try {
    const res = await axios.get(`${PYTHON_URL}/api/v1/profile/signature`, {
      params: { portal_user_id: portalUserId },
    });
    const data = res?.data?.data || {};
    return !!data.has_signature;
  } catch (_) {
    return false;
  }
}

async function getSignaturePayload(portalUserId) {
  if (!portalUserId) return null;
  try {
    const res = await axios.get(`${PYTHON_URL}/api/v1/profile/signature`, {
      params: { portal_user_id: String(portalUserId) },
    });
    const d = res?.data?.data || {};
    if (!d.has_signature) return null;
    return {
      signature_data: d.signature_data || null,
      signature_image_url: d.signature_image_url || null,
      signature_type: d.signature_type || null,
      signature_text: "Signed",
    };
  } catch (_) {
    return null;
  }
}

async function getUserDisplayPayload(portalUserId) {
  if (!portalUserId) return null;
  try {
    const res = await axios.get(`${PYTHON_URL}/api/v1/profile`, {
      params: { portal_user_id: String(portalUserId) },
    });
    const d = res?.data?.data || {};
    return {
      name: d.fullName || d.full_name || d.display_name || null,
      title: d.title || null,
      dept_code: d.dept_code || null,
      department: d.department || null,
    };
  } catch (_) {
    return null;
  }
}

async function enrichProcessApprovalSignatures(process) {
  if (!process || !process.approval_summary) return process;
  const approval = process.approval_summary || {};
  const steps = process.steps || [];

  const requestedId = process.employee_id ? String(process.employee_id) : null;
  const verifiedId = steps.find((s) => s.step_number === 2 && ["approve", "reject"].includes(s.action))?.actor_id || null;
  const checkedId = steps.find((s) => s.step_number === 4 && ["approve", "authorize", "reject"].includes(s.action))?.actor_id || null;
  const approvedId = steps.find((s) => s.step_number === 5 && ["approve", "reject", "authorize"].includes(s.action))?.actor_id || null;

  const [
    requestedSig,
    verifiedSig,
    checkedSig,
    approvedSig,
    requestedUser,
    verifiedUser,
    checkedUser,
    approvedUser,
  ] = await Promise.all([
    getSignaturePayload(requestedId),
    getSignaturePayload(verifiedId),
    getSignaturePayload(checkedId),
    getSignaturePayload(approvedId),
    getUserDisplayPayload(requestedId),
    getUserDisplayPayload(verifiedId),
    getUserDisplayPayload(checkedId),
    getUserDisplayPayload(approvedId),
  ]);

  process.approval_summary = {
    ...approval,
    requested: { ...(approval.requested || {}), ...(requestedUser || {}), ...(requestedSig || {}) },
    verified: { ...(approval.verified || {}), ...(verifiedUser || {}), ...(verifiedSig || {}) },
    checked: { ...(approval.checked || {}), ...(checkedUser || {}), ...(checkedSig || {}) },
    approved: { ...(approval.approved || {}), ...(approvedUser || {}), ...(approvedSig || {}) },
  };

  // Enrich step actor names with user title when actor_name is missing/unknown.
  const uniqueActorIds = [...new Set((steps || []).map((s) => s?.actor_id).filter(Boolean).map(String))];
  if (uniqueActorIds.length) {
    const actorProfilePairs = await Promise.all(
      uniqueActorIds.map(async (id) => [id, await getUserDisplayPayload(id)])
    );
    const actorProfileMap = Object.fromEntries(actorProfilePairs);

    process.steps = (steps || []).map((s) => {
      const rawName = String(s?.actor_name || "").trim().toLowerCase();
      const isUnknown = !rawName || rawName === "unknown";
      if (!isUnknown) return s;
      const title = actorProfileMap[String(s?.actor_id)]?.title;
      return {
        ...s,
        actor_name: title || s?.actor_name || null,
      };
    });
  }
  return process;
}

const offboardingService = {
  async list(reqUser, { page = 1, page_size = 20, status } = {}) {
    const params = { page, page_size };

    if (reqUser?.role_id === ROLE_SUPER) {
      // thấy tất cả
    } else if (reqUser?.role_id === ROLE_ADMIN) {
      params.tenant_id = reqUser.tenant_id;
    } else {
      params.employee_id = getUserId(reqUser);
    }

    if (status) params.status = status;

    const res = await axios.get(`${BASE}/processes`, { params });
    const payload = res.data.data || {};
    const items = Array.isArray(payload.items) ? payload.items : [];
    await Promise.all(items.map(enrichProcessApprovalSignatures));
    return payload;
  },

  async create(reqUser, payload = {}) {
    const actorProfile = await getUserDisplayPayload(getUserId(reqUser));
    const actorCtx = resolveActorContext(reqUser, actorProfile);
    const actorDeptCode = actorCtx.deptCode || actorCtx.department;
    if (!canSubmitByDeptCode(actorDeptCode)) {
      return { error: "FORBIDDEN", message: "Chỉ nhân sự cấp nhân viên mới được nộp đơn nghỉ việc." };
    }
    const body = {
      tenant_id: reqUser?.tenant_id || null,
      employee_id: getUserId(reqUser),
      employee_name: payload.full_name || getUserName(reqUser),
      employee_code: payload.e_code || payload.hr_code || null,
      dept_code: payload.dept_code || payload.department || null,
      department: payload.department_name || payload.dept_code || payload.department || null,
      job_title: payload.title || null,
      joining_date: payload.joining_date || null,
      last_working_day: payload.last_working_day || null,
      contract_type: payload.contract_type || "DEFINITE",
      reason_for_resignation: payload.reason_for_resignation || "",
      commitment_accepted: !!payload.commitment_accepted,
      actor_id: getUserId(reqUser),
      actor_name: getUserName(reqUser),
    };

    const res = await axios.post(`${BASE}/processes`, body);
    const process = res.data.data;
    await enrichProcessApprovalSignatures(process);
    return process;
  },

  async getById(reqUser, id) {
    let res;
    try {
      res = await axios.get(`${BASE}/processes/${id}`);
    } catch (e) {
      if (e.response?.status === 404) return null;
      throw e;
    }

    const p = res.data.data;
    if (!p) return null;

    // Permission check on gateway side
    await enrichProcessApprovalSignatures(p);
    if (reqUser?.role_id === ROLE_SUPER) return p;
    if (reqUser?.role_id === ROLE_ADMIN && p.tenant_id === reqUser.tenant_id) return p;
    if (String(p.employee_id) === String(getUserId(reqUser))) return p;
    return "FORBIDDEN";
  },

  async takeAction(reqUser, id, stepNumber, payload = {}) {
    // Permission check on gateway side
    let process;
    try {
      const r = await axios.get(`${BASE}/processes/${id}`);
      process = r.data.data;
    } catch (e) {
      if (e.response?.status === 404) return { error: "NOT_FOUND" };
      throw e;
    }

    if (!process) return { error: "NOT_FOUND" };

    // View permission
    const canView =
      reqUser?.role_id === ROLE_SUPER ||
      (reqUser?.role_id === ROLE_ADMIN && process.tenant_id === reqUser.tenant_id) ||
      String(process.employee_id) === String(getUserId(reqUser));
    if (!canView) return { error: "FORBIDDEN" };

    const actorProfile = await getUserDisplayPayload(getUserId(reqUser));
    const actorCtx = resolveActorContext(reqUser, actorProfile);
    const actorDeptCode = actorCtx.deptCode || actorCtx.department;
    const processDeptCode = normalizeUpper(process?.dept_code || process?.department || "");
    if (!canTakeWorkflowStepAction(actorDeptCode, actorCtx.title, processDeptCode, stepNumber)) {
      return { error: "FORBIDDEN", message: "Bạn không có quyền thao tác bước này theo phòng ban/chức danh." };
    }
    if (stepNumber >= 2) {
      const hasSignature = await hasUserSignature(reqUser);
      if (!hasSignature) return { error: "MISSING_SIGNATURE" };
    }

    const body = {
      action: payload.action,
      note: payload.note || null,
      actor_id: getUserId(reqUser),
      actor_name: getUserName(reqUser),
      extra: payload,
    };

    const res = await axios.post(`${BASE}/processes/${id}/steps/${stepNumber}/action`, body);
    if (res?.data?.data) await enrichProcessApprovalSignatures(res.data.data);
    return res.data;
  },

  async confirmHandover(reqUser, id, hoKey, notes) {
    if (!["ho1", "ho2", "ho3"].includes(hoKey)) return { error: "BAD_REQUEST" };

    let process;
    try {
      const r = await axios.get(`${BASE}/processes/${id}`);
      process = r.data.data;
    } catch (e) {
      if (e.response?.status === 404) return { error: "NOT_FOUND" };
      throw e;
    }
    if (!process) return { error: "NOT_FOUND" };

    const canView =
      reqUser?.role_id === ROLE_SUPER ||
      (reqUser?.role_id === ROLE_ADMIN && process.tenant_id === reqUser.tenant_id) ||
      String(process.employee_id) === String(getUserId(reqUser));
    if (!canView) return { error: "FORBIDDEN" };

    const actorProfile = await getUserDisplayPayload(getUserId(reqUser));
    const actorCtx = resolveActorContext(reqUser, actorProfile);
    const actorDeptCode = actorCtx.deptCode || actorCtx.department;
    const processDeptCode = normalizeUpper(process?.dept_code || process?.department || "");
    if (!canTakeHandoverAction(actorDeptCode, actorCtx.title, processDeptCode, hoKey)) {
      return { error: "FORBIDDEN", message: "Bạn không có quyền xác nhận hạng mục bàn giao này." };
    }
    if (!(await hasUserSignature(reqUser))) return { error: "MISSING_SIGNATURE" };
    const body = {
      notes: notes || null,
      actor_id: getUserId(reqUser),
      actor_name: actorProfile?.name || getUserName(reqUser),
    };

    const res = await axios.post(`${BASE}/processes/${id}/handover/${hoKey}/confirm`, body);
    if (res?.data?.data) await enrichProcessApprovalSignatures(res.data.data);
    return res.data;
  },

  async rejectHandover(reqUser, id, hoKey, reason) {
    if (!["ho1", "ho2", "ho3"].includes(hoKey)) return { error: "BAD_REQUEST" };
    if (!reason || !String(reason).trim()) return { error: "BAD_REQUEST", message: "Lý do reject là bắt buộc" };

    let process;
    try {
      const r = await axios.get(`${BASE}/processes/${id}`);
      process = r.data.data;
    } catch (e) {
      if (e.response?.status === 404) return { error: "NOT_FOUND" };
      throw e;
    }
    if (!process) return { error: "NOT_FOUND" };

    const canView =
      reqUser?.role_id === ROLE_SUPER ||
      (reqUser?.role_id === ROLE_ADMIN && process.tenant_id === reqUser.tenant_id) ||
      String(process.employee_id) === String(getUserId(reqUser));
    if (!canView) return { error: "FORBIDDEN" };

    const actorProfile = await getUserDisplayPayload(getUserId(reqUser));
    const actorCtx = resolveActorContext(reqUser, actorProfile);
    const actorDeptCode = actorCtx.deptCode || actorCtx.department;
    const processDeptCode = normalizeUpper(process?.dept_code || process?.department || "");
    if (!canTakeHandoverAction(actorDeptCode, actorCtx.title, processDeptCode, hoKey)) {
      return { error: "FORBIDDEN", message: "Bạn không có quyền reject hạng mục bàn giao này." };
    }
    if (!(await hasUserSignature(reqUser))) return { error: "MISSING_SIGNATURE" };
    const body = {
      reason: String(reason).trim(),
      actor_id: getUserId(reqUser),
      actor_name: actorProfile?.name || getUserName(reqUser),
    };

    const res = await axios.post(`${BASE}/processes/${id}/handover/${hoKey}/reject`, body);
    if (res?.data?.data) await enrichProcessApprovalSignatures(res.data.data);
    return res.data;
  },

  async handoverTimelineAction(reqUser, id, hoKey, payload = {}) {
    if (!["ho1", "ho2", "ho3"].includes(hoKey)) return { error: "BAD_REQUEST", message: "Handover key không hợp lệ" };
    const action = String(payload.action || "").toLowerCase();
    if (!["verify", "authenticate", "sign", "complete"].includes(action)) {
      return { error: "BAD_REQUEST", message: "Timeline action không hợp lệ" };
    }

    let process;
    try {
      const r = await axios.get(`${BASE}/processes/${id}`);
      process = r.data.data;
    } catch (e) {
      if (e.response?.status === 404) return { error: "NOT_FOUND" };
      throw e;
    }
    if (!process) return { error: "NOT_FOUND" };

    const isEmployee = isProcessEmployee(reqUser, process);
    const actorProfile = await getUserDisplayPayload(getUserId(reqUser));
    const actorCtx = resolveActorContext(reqUser, actorProfile);
    const actorDeptCode = actorCtx.deptCode || actorCtx.department;
    const processDeptCode = normalizeUpper(process?.dept_code || process?.department || "");
    const canApproverAct = canTakeHandoverAction(actorDeptCode, actorCtx.title, processDeptCode, hoKey);

    if (action === "verify" && !isEmployee) {
      return { error: "FORBIDDEN", message: "Chỉ nhân viên mới có thể xác thực biên bản." };
    }
    if (["authenticate", "sign", "complete"].includes(action) && !canApproverAct) {
      return { error: "FORBIDDEN", message: "Bạn không có quyền xác thực/ký/complete biên bản này." };
    }
    if (!(await hasUserSignature(reqUser))) return { error: "MISSING_SIGNATURE" };

    const body = {
      action,
      note: payload.note || null,
      actor_id: getUserId(reqUser),
      actor_name: actorProfile?.name || getUserName(reqUser),
    };
    const res = await axios.post(`${BASE}/processes/${id}/handover/${hoKey}/timeline-action`, body);
    if (res?.data?.data) await enrichProcessApprovalSignatures(res.data.data);
    return res.data;
  },

  async saveHandoverContent(reqUser, id, hoKey, content) {
    if (!["ho1", "ho2", "ho3"].includes(hoKey)) return { error: "BAD_REQUEST" };

    let process;
    try {
      const r = await axios.get(`${BASE}/processes/${id}`);
      process = r.data.data;
    } catch (e) {
      if (e.response?.status === 404) return { error: "NOT_FOUND" };
      throw e;
    }
    if (!process) return { error: "NOT_FOUND" };

    const actorId = String(getUserId(reqUser) || "");
    const isEmployee = isProcessEmployee(reqUser, process);
    const isAdmin = isAdminLike(reqUser);
    const actorProfile = await getUserDisplayPayload(actorId);
    const actorCtx = resolveActorContext(reqUser, actorProfile);
    const actorDeptCode = actorCtx.deptCode || actorCtx.department;
    const processDeptCode = normalizeUpper(process?.dept_code || process?.department || "");
    const canApproverAct = canTakeHandoverAction(actorDeptCode, actorCtx.title, processDeptCode, hoKey);

    if (!isEmployee && !isAdmin && !canApproverAct) {
      return { error: "FORBIDDEN", message: "Bạn không có quyền lưu nội dung biên bản này." };
    }

    const res = await axios.patch(`${BASE}/processes/${id}/handover/${hoKey}/content`, { content: content || {} });
    return res.data;
  },

  async resetHandover(reqUser, id, hoKey, reason) {
    if (!["ho1", "ho2", "ho3"].includes(hoKey)) return { error: "BAD_REQUEST" };
    if (!isAdminLike(reqUser)) return { error: "FORBIDDEN", message: "Chỉ admin mới có thể reset biên bản." };

    const actorProfile = await getUserDisplayPayload(getUserId(reqUser));
    const body = {
      reason: reason || null,
      actor_id: getUserId(reqUser),
      actor_name: actorProfile?.name || getUserName(reqUser),
    };
    try {
      const res = await axios.post(`${BASE}/processes/${id}/handover/${hoKey}/reset`, body);
      return res.data;
    } catch (e) {
      if (e.response?.status === 404) return { error: "NOT_FOUND" };
      throw e;
    }
  },

  async overrideReturn(reqUser, id, reason) {
    if (!isAdminLike(reqUser)) return { error: "FORBIDDEN" };
    if (!(await hasUserSignature(reqUser))) return { error: "MISSING_SIGNATURE" };

    let process;
    try {
      const r = await axios.get(`${BASE}/processes/${id}`);
      process = r.data.data;
    } catch (e) {
      if (e.response?.status === 404) return { error: "NOT_FOUND" };
      throw e;
    }
    if (!process) return { error: "NOT_FOUND" };

    const body = {
      reason: reason || null,
      actor_id: getUserId(reqUser),
      actor_name: getUserName(reqUser),
    };

    const res = await axios.post(`${BASE}/processes/${id}/override/return-handover`, body);
    if (res?.data?.data) await enrichProcessApprovalSignatures(res.data.data);
    return res.data;
  },

  async resendConfirmation(reqUser, id) {
    if (!isAdminLike(reqUser) && !isSuper(reqUser)) return { error: "FORBIDDEN" };

    let process;
    try {
      const r = await axios.get(`${BASE}/processes/${id}`);
      process = r.data.data;
    } catch (e) {
      if (e.response?.status === 404) return { error: "NOT_FOUND" };
      throw e;
    }
    if (!process) return { error: "NOT_FOUND" };

    const canView =
      reqUser?.role_id === ROLE_SUPER ||
      (reqUser?.role_id === ROLE_ADMIN && process.tenant_id === reqUser.tenant_id);
    if (!canView) return { error: "FORBIDDEN" };

    const res = await axios.post(`${BASE}/processes/${id}/resend-confirmation`, {});
    return res.data;
  },

  async listApprovalLogs(_reqUser, query = {}) {
    const params = {
      page: Number(query.page || 1),
      page_size: Number(query.page_size || 20),
    };
    if (query.document_type) params.document_type = query.document_type;
    if (query.actor) params.actor = query.actor;
    if (query.from_date) params.from_date = query.from_date;
    if (query.to_date) params.to_date = query.to_date;
    const res = await axios.get(`${BASE}/sign-hub/approval-logs`, { params });
    return res.data?.data || { items: [], total: 0, page: 1, page_size: 20 };
  },

};

module.exports = offboardingService;
