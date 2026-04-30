-- =============================================================
-- Migration: Tạo bảng permissions + roles, seed data mặc định
-- Migrate users.role từ string cũ ("member","admin","superAdmin")
--   sang role_id mới (10 chữ số)
-- Idempotent — chạy nhiều lần không bị lỗi
-- =============================================================

-- 1. Tạo bảng permissions
CREATE TABLE IF NOT EXISTS permissions (
    permission_id VARCHAR(10) PRIMARY KEY,
    name          VARCHAR(100) UNIQUE NOT NULL,
    description   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Tạo bảng roles
CREATE TABLE IF NOT EXISTS roles (
    role_id     VARCHAR(10) PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    permissions TEXT[] NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Seed permissions (idempotent)
INSERT INTO permissions (permission_id, name, description) VALUES
    ('1000000001', 'bookings',      'Quản lý đặt phòng họp'),
    ('1000000002', 'editor',        'Thiết kế email'),
    ('1000000003', 'email-lists',   'Danh sách khách hàng'),
    ('1000000004', 'templates',     'Mẫu email'),
    ('1000000005', 'notifications', 'Thông báo hệ thống'),
    ('1000000006', 'settings',      'Cài đặt hệ thống'),
    ('1000000007', 'user',          'Quản lý người dùng'),
    ('1000000008', 'dashboard',     'Dashboard tổng quan')
ON CONFLICT (permission_id) DO NOTHING;

-- 4. Seed roles (idempotent)
INSERT INTO roles (role_id, name, description, permissions) VALUES
    (
        '2000000001',
        'superAdmin',
        'Quản trị toàn hệ thống',
        ARRAY['1000000001','1000000002','1000000003','1000000004',
              '1000000005','1000000006','1000000007','1000000008']
    ),
    (
        '2000000002',
        'admin',
        'Quản trị tenant — không có settings',
        ARRAY['1000000001','1000000002','1000000003','1000000004',
              '1000000005','1000000007','1000000008']
    ),
    (
        '2000000003',
        'member',
        'Thành viên — bookings, editor, email-lists',
        ARRAY['1000000001','1000000002','1000000003','1000000008']
    )
ON CONFLICT (role_id) DO NOTHING;

-- 5. Migrate users.role: đổi string cũ → role_id mới
--    Chỉ cập nhật các row còn chứa tên cũ (không phải 10 chữ số)
UPDATE users SET role = '2000000001'
WHERE role = 'superAdmin'
  AND role NOT SIMILAR TO '[0-9]{10}';

UPDATE users SET role = '2000000002'
WHERE role = 'admin'
  AND role NOT SIMILAR TO '[0-9]{10}';

UPDATE users SET role = '2000000003'
WHERE role IN ('member', 'meetingAdmin')
  AND role NOT SIMILAR TO '[0-9]{10}';

-- 6. Đặt default mới cho cột users.role
ALTER TABLE users ALTER COLUMN role SET DEFAULT '2000000003';

-- Done
SELECT 'Migration completed successfully.' AS status;
