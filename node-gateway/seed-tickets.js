/**
 * seed-tickets.js
 * Chạy: node seed-tickets.js
 * Ghi thẳng ticket mẫu vào Redis — không cần gateway đang chạy.
 *
 * Users thật từ DB:
 *   superAdmin : id=888,  name="Quyen Nguyen",  email=at128ve@gmail.com,     tenant=tenant_tran_duc_corp
 *   admin      : id=999,  name="My Đậu",        email=daumy848@gmail.com,     tenant=tenant_meeting_enterprise
 *   member     : id=1005, name="Bi Le",          email=traile.bi@gmail.com,    tenant=tenant_meeting_enterprise
 */

require('dotenv').config();
const { createClient } = require('redis');

const REDIS_URL  = process.env.REDIS_URL || 'redis://:Quyen20262027@localhost:6379';
const TTL        = 60 * 60 * 24 * 365;
const GUEST_TENANT = '__guest__';

const SUPER = { id: '888',  name: 'Quyen Nguyen', email: 'at128ve@gmail.com',   tenant: 'tenant_tran_duc_corp',       role: '2000000001' };
const ADMIN = { id: '999',  name: 'My Đậu',       email: 'daumy848@gmail.com',  tenant: 'tenant_meeting_enterprise',  role: '2000000002' };
const MEMBER= { id: '1005', name: 'Bi Le',         email: 'traile.bi@gmail.com', tenant: 'tenant_meeting_enterprise',  role: '2000000003' };

const client = createClient({ url: REDIS_URL });
client.on('error', e => console.error('Redis error:', e));

// ── Helpers ────────────────────────────────────────────────────────────────────

const ticketKey  = (tenantId, id) => `ticket:${tenantId}:${id}`;
const indexKey   = (tenantId)     => `ticket_index:${tenantId}`;
const counterKey = (tenantId)     => `ticket_counter:${tenantId}`;

async function nextNum(tenantId) {
  const n = await client.incr(counterKey(tenantId));
  return `T-${String(n).padStart(4, '0')}`;
}

async function save(tenantId, ticket) {
  await client.set(ticketKey(tenantId, ticket._id), JSON.stringify(ticket), { EX: TTL });
  await client.sAdd(indexKey(tenantId), ticket._id);
}

const uid  = () => `ticket_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
const now  = new Date();
const ago  = (days, hours = 0) => { const d = new Date(now); d.setDate(d.getDate() - days); d.setHours(d.getHours() - hours); return d.toISOString(); };

const base = (overrides) => ({
  comments: [], attachments: [], resolution: '', resolvedBy: null, resolvedAt: null,
  contactEmail: '', emailNotification: false, source: 'direct',
  ...overrides,
});

// ── Seed ───────────────────────────────────────────────────────────────────────

async function seed() {
  await client.connect();
  console.log('✅ Redis connected');

  const results = [];

  // ═══════════════════════════════════════════════════════════════════
  // 1. Ticket của MEMBER → admin (999) cùng tenant xử lý
  // ═══════════════════════════════════════════════════════════════════
  const memberTickets = [
    base({
      subject:       'Không thể đặt phòng họp vào thứ Sáu',
      description:   'Khi chọn phòng họp A3 vào thứ Sáu tuần tới hệ thống báo "Slot không khả dụng" dù lịch hiển thị còn trống. Tôi đã thử đặt 3 lần vẫn lỗi.',
      category: 'bug', priority: 'high', status: 'in_progress',
      tenantId: MEMBER.tenant, userId: MEMBER.id, userEmail: MEMBER.email, userName: MEMBER.name, createdByRole: MEMBER.role,
      createdAt: ago(3), updatedAt: ago(1),
      comments: [{
        _id: `cmt_${Date.now()}_1`, message: 'Chúng tôi đã ghi nhận lỗi, đang kiểm tra module booking. Bạn có thể tạm thời dùng phòng B1 trong khi chờ không?',
        userId: ADMIN.id, userName: ADMIN.name, isAdmin: true, isSuperAdmin: false, attachments: [], createdAt: ago(1, 2),
      }],
    }),
    base({
      subject:       'Yêu cầu thêm tính năng nhắc nhở trước 15 phút',
      description:   'Hệ thống hiện chỉ nhắc trước 5 phút. Tôi muốn có tùy chọn nhắc trước 15 hoặc 30 phút qua email để chuẩn bị tài liệu kịp.',
      category: 'feature', priority: 'medium', status: 'resolved',
      tenantId: MEMBER.tenant, userId: MEMBER.id, userEmail: MEMBER.email, userName: MEMBER.name, createdByRole: MEMBER.role,
      createdAt: ago(10), updatedAt: ago(2),
      resolution: 'Đã bổ sung tùy chọn nhắc 15 phút và 30 phút trong phần Cài đặt > Thông báo. Vui lòng F5 lại app.',
      resolvedAt: ago(2),
      resolvedBy: { userId: ADMIN.id, userName: ADMIN.name, role_id: ADMIN.role },
    }),
    base({
      subject:       'Hỏi về cách xuất báo cáo cuộc họp ra Excel',
      description:   'Tôi cần xuất danh sách cuộc họp trong tháng ra file Excel để nộp báo cáo cho ban giám đốc. Hệ thống có hỗ trợ tính năng này chưa?',
      category: 'question', priority: 'low', status: 'open',
      tenantId: MEMBER.tenant, userId: MEMBER.id, userEmail: MEMBER.email, userName: MEMBER.name, createdByRole: MEMBER.role,
      createdAt: ago(1), updatedAt: ago(1),
    }),
    base({
      subject:       'Lỗi upload avatar — file PNG bị từ chối',
      description:   'Khi upload ảnh đại diện định dạng PNG (3MB) hệ thống báo lỗi "Unsupported format". JPG thì upload được bình thường.',
      category: 'bug', priority: 'medium', status: 'waiting',
      tenantId: MEMBER.tenant, userId: MEMBER.id, userEmail: MEMBER.email, userName: MEMBER.name, createdByRole: MEMBER.role,
      createdAt: ago(4), updatedAt: ago(1, 4),
      comments: [{
        _id: `cmt_${Date.now()}_2`, message: 'Bạn có thể gửi cho tôi file PNG đó không? Tôi cần kiểm tra xem lỗi ở encoding hay ở size limit.',
        userId: ADMIN.id, userName: ADMIN.name, isAdmin: true, isSuperAdmin: false, attachments: [], createdAt: ago(1, 4),
      }],
    }),
  ];

  for (const t of memberTickets) {
    const id  = uid();
    const num = await nextNum(MEMBER.tenant);
    await save(MEMBER.tenant, { _id: id, ticketNumber: num, ...t });
    results.push({ ticketNumber: num, from: 'member → admin xử lý', status: t.status });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 2. Ticket của ADMIN → superAdmin (888) xử lý
  // ═══════════════════════════════════════════════════════════════════
  const adminTickets = [
    base({
      subject:       'Yêu cầu cấp quyền tự cấu hình SMTP cho tenant',
      description:   'Tenant chúng tôi cần dùng SMTP server riêng (Office 365) thay vì SMTP mặc định của hệ thống để đảm bảo email đi từ domain doanh nghiệp. Nhờ superAdmin cấp quyền email-config.',
      category: 'feature', priority: 'high', status: 'waiting',
      tenantId: ADMIN.tenant, userId: ADMIN.id, userEmail: ADMIN.email, userName: ADMIN.name, createdByRole: ADMIN.role,
      createdAt: ago(5), updatedAt: ago(1),
      comments: [{
        _id: `cmt_${Date.now()}_3`, message: 'Đã nhận yêu cầu. Đang xem xét chính sách bảo mật trước khi cấp quyền. Sẽ phản hồi trong 2 ngày làm việc.',
        userId: SUPER.id, userName: SUPER.name, isAdmin: true, isSuperAdmin: true, attachments: [], createdAt: ago(1, 6),
      }],
    }),
    base({
      subject:       'Báo lỗi import danh sách user hàng loạt bị timeout',
      description:   'Khi import file CSV có 200+ user, hệ thống timeout sau 30 giây và không có user nào được tạo. File CSV đúng template. Đã thử nhiều lần, cùng một kết quả.',
      category: 'bug', priority: 'urgent', status: 'in_progress',
      tenantId: ADMIN.tenant, userId: ADMIN.id, userEmail: ADMIN.email, userName: ADMIN.name, createdByRole: ADMIN.role,
      createdAt: ago(2), updatedAt: ago(0, 3),
    }),
    base({
      subject:       'Đề nghị thêm dashboard thống kê phòng họp theo tháng',
      description:   'Quản lý cần xem thống kê: phòng nào được đặt nhiều nhất, giờ cao điểm, tỷ lệ hủy theo từng tháng. Hiện tại phải export thủ công rất mất thời gian.',
      category: 'feature', priority: 'medium', status: 'open',
      tenantId: ADMIN.tenant, userId: ADMIN.id, userEmail: ADMIN.email, userName: ADMIN.name, createdByRole: ADMIN.role,
      createdAt: ago(7), updatedAt: ago(7),
    }),
  ];

  for (const t of adminTickets) {
    const id  = uid();
    const num = await nextNum(ADMIN.tenant);
    await save(ADMIN.tenant, { _id: id, ticketNumber: num, ...t });
    results.push({ ticketNumber: num, from: 'admin → superAdmin xử lý', status: t.status });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 3. Ticket của SUPERADMIN — tự tạo, tự giải quyết được
  // ═══════════════════════════════════════════════════════════════════
  const superTickets = [
    base({
      subject:       'Migrate Redis standalone sang Redis Cluster 3-node',
      description:   'Cần migrate Redis standalone lên Redis Cluster 3-node để đảm bảo HA cho production. Lên kế hoạch maintenance window vào 2h sáng thứ Bảy.',
      category: 'feature', priority: 'urgent', status: 'resolved',
      tenantId: SUPER.tenant, userId: SUPER.id, userEmail: SUPER.email, userName: SUPER.name, createdByRole: SUPER.role,
      createdAt: ago(14), updatedAt: ago(7),
      resolution: 'Đã migrate xong Redis Cluster 3-node lúc 3h15 sáng. Monitor 24h không có alert. Đóng ticket.',
      resolvedAt: ago(7),
      resolvedBy: { userId: SUPER.id, userName: SUPER.name, role_id: SUPER.role },
    }),
    base({
      subject:       'Review bảo mật JWT token expiry cho toàn hệ thống',
      description:   'Cần review lại thời gian expire của JWT (hiện 24h) và refresh token policy để đảm bảo compliance với tiêu chuẩn bảo mật nội bộ Q2/2026.',
      category: 'question', priority: 'high', status: 'in_progress',
      tenantId: SUPER.tenant, userId: SUPER.id, userEmail: SUPER.email, userName: SUPER.name, createdByRole: SUPER.role,
      createdAt: ago(3), updatedAt: ago(1),
    }),
  ];

  for (const t of superTickets) {
    const id  = uid();
    const num = await nextNum(SUPER.tenant);
    await save(SUPER.tenant, { _id: id, ticketNumber: num, ...t });
    results.push({ ticketNumber: num, from: 'superAdmin (tự xử lý)', status: t.status });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 4. Ticket từ /contact (guest) — chỉ superAdmin thấy
  // ═══════════════════════════════════════════════════════════════════
  const guestTickets = [
    base({
      subject:       'Muốn dùng thử enterprise plan cho công ty 50 người',
      description:   'Chúng tôi là startup fintech ~50 người, đang cần giải pháp quản lý cuộc họp nội bộ. Muốn trải nghiệm bản enterprise 30 ngày trước khi ký hợp đồng. Liên hệ: cto@fintechvn.com',
      category: 'billing', priority: 'high', status: 'open',
      tenantId: GUEST_TENANT, userId: null, userEmail: 'cto@fintechvn.com', userName: 'Khách', createdByRole: 'guest',
      contactEmail: 'cto@fintechvn.com', emailNotification: true, source: 'contact_form',
      createdAt: ago(1), updatedAt: ago(1),
    }),
    base({
      subject:       'Trang đăng nhập không load được trên Safari 17',
      description:   'macOS Ventura + Safari 17: trang /login bị trắng hoàn toàn sau 2s. Console báo lỗi "Content Security Policy". Chrome/Firefox bình thường. Đã clear cache vẫn bị.',
      category: 'bug', priority: 'medium', status: 'resolved',
      tenantId: GUEST_TENANT, userId: null, userEmail: 'user@example.com', userName: 'Khách', createdByRole: 'guest',
      contactEmail: 'user@example.com', emailNotification: true, source: 'contact_form',
      createdAt: ago(6), updatedAt: ago(3),
      resolution: 'Đã fix CSP header thiếu safari vendor prefix. Deploy production 2h sáng. Vui lòng thử lại.',
      resolvedAt: ago(3),
      resolvedBy: { userId: SUPER.id, userName: SUPER.name, role_id: SUPER.role },
      comments: [{
        _id: `cmt_${Date.now()}_4`, message: 'Đã tái hiện được lỗi trên Safari 17. Nguyên nhân: CSP header thiếu webkit-src. Đang fix.',
        userId: SUPER.id, userName: SUPER.name, isAdmin: true, isSuperAdmin: true, attachments: [], createdAt: ago(4),
      }],
    }),
    base({
      subject:       'Hỏi về chính sách bảo mật dữ liệu doanh nghiệp',
      description:   'Công ty chúng tôi sắp audit SOC2. Cần biết dữ liệu cuộc họp được mã hóa thế nào, lưu ở đâu, ai có quyền truy cập, và chính sách xóa dữ liệu khi hủy hợp đồng.',
      category: 'question', priority: 'high', status: 'open',
      tenantId: GUEST_TENANT, userId: null, userEmail: 'security@techcorp.vn', userName: 'Khách', createdByRole: 'guest',
      contactEmail: 'security@techcorp.vn', emailNotification: true, source: 'contact_form',
      createdAt: ago(0, 5), updatedAt: ago(0, 5),
    }),
  ];

  // Guest dùng counter riêng để ra số G-XXXX
  const guestCounterKey = `ticket_counter:${GUEST_TENANT}`;
  for (const t of guestTickets) {
    const id  = uid();
    const n   = await client.incr(guestCounterKey);
    const num = `G-${String(n).padStart(4, '0')}`;
    await save(GUEST_TENANT, { _id: id, ticketNumber: num, ...t });
    results.push({ ticketNumber: num, from: 'guest /contact (superAdmin xử lý)', status: t.status });
  }

  // ── Kết quả ────────────────────────────────────────────────────────
  console.log('\n✅ Seed hoàn tất — ' + results.length + ' ticket đã ghi vào Redis:\n');
  const pad = (s, n) => String(s).padEnd(n);
  console.log(pad('Ticket#', 10) + pad('Status', 16) + 'Scope');
  console.log('─'.repeat(70));
  results.forEach(r => console.log(pad(r.ticketNumber, 10) + pad(r.status, 16) + r.from));
  console.log('');

  await client.quit();
}

seed().catch(e => { console.error('❌ Seed lỗi:', e); process.exit(1); });
