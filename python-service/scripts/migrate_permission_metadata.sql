-- =============================================================
-- Migration: Thêm metadata columns vào bảng permissions
--            + tách email-config thành permission riêng
-- Idempotent — chạy nhiều lần không bị lỗi
-- =============================================================

-- 1. Thêm 4 cột mới vào bảng permissions (nếu chưa có)
ALTER TABLE permissions
    ADD COLUMN IF NOT EXISTS app_path    TEXT,
    ADD COLUMN IF NOT EXISTS app_icon    TEXT,
    ADD COLUMN IF NOT EXISTS app_group   VARCHAR(50),
    ADD COLUMN IF NOT EXISTS parent_name VARCHAR(100);

-- 2. Patch metadata cho 8 permissions cũ
UPDATE permissions SET
    app_path   = '/bookings',
    app_icon   = 'bi bi-calendar-check',
    app_group  = 'admin',
    parent_name = NULL
WHERE permission_id = '1000000001';

UPDATE permissions SET
    app_path   = '/editor',
    app_icon   = 'bi bi-pencil-square',
    app_group  = 'email',
    parent_name = NULL
WHERE permission_id = '1000000002';

UPDATE permissions SET
    app_path   = '/email-lists',
    app_icon   = 'bi bi-person-lines-fill',
    app_group  = 'email',
    parent_name = NULL
WHERE permission_id = '1000000003';

UPDATE permissions SET
    app_path   = '/templates',
    app_icon   = 'bi bi-layout-text-window-reverse',
    app_group  = 'email',
    parent_name = NULL
WHERE permission_id = '1000000004';

UPDATE permissions SET
    app_path   = '/notifications',
    app_icon   = 'bi bi-bell',
    app_group  = 'system',
    parent_name = NULL
WHERE permission_id = '1000000005';

UPDATE permissions SET
    app_path   = '/settings',
    app_icon   = 'bi bi-gear',
    app_group  = 'settings',
    parent_name = NULL
WHERE permission_id = '1000000006';

UPDATE permissions SET
    app_path   = '/user',
    app_icon   = 'bi bi-people',
    app_group  = 'system',
    parent_name = NULL
WHERE permission_id = '1000000007';

UPDATE permissions SET
    app_path   = '/dashboard',
    app_icon   = 'bi bi-speedometer2',
    app_group  = 'admin',
    parent_name = NULL
WHERE permission_id = '1000000008';

-- 3. Insert permission mới cho email-config (tách riêng khỏi settings)
INSERT INTO permissions (permission_id, name, description, app_path, app_icon, app_group, parent_name)
VALUES (
    '1000000009',
    'email-config',
    'Cấu hình email server',
    '/settings/email-config',
    'bi bi-gear-wide-connected',
    'settings',
    'settings'
)
ON CONFLICT (permission_id) DO UPDATE SET
    app_path    = EXCLUDED.app_path,
    app_icon    = EXCLUDED.app_icon,
    app_group   = EXCLUDED.app_group,
    parent_name = EXCLUDED.parent_name;

-- 4. Cập nhật roles: thêm email-config vào superAdmin, giữ nguyên admin/member
UPDATE roles
SET permissions = ARRAY[
    '1000000001','1000000002','1000000003','1000000004',
    '1000000005','1000000006','1000000007','1000000008','1000000009'
]
WHERE role_id = '2000000001';

-- admin: không có settings (1000000006) và không có email-config (1000000009)
UPDATE roles
SET permissions = ARRAY[
    '1000000001','1000000002','1000000003','1000000004',
    '1000000005','1000000007','1000000008'
]
WHERE role_id = '2000000002';

-- 5. Update SQL migration cũ: xóa description cũ
UPDATE roles SET description = 'Quản trị toàn hệ thống'  WHERE role_id = '2000000001';
UPDATE roles SET description = 'Quản trị tenant'         WHERE role_id = '2000000002';
UPDATE roles SET description = 'Thành viên'              WHERE role_id = '2000000003';

SELECT 'Migration permission metadata completed.' AS status;
