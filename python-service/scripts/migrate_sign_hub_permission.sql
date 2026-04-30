-- =============================================================
-- Migration: Add Sign Hub permission under HRM group
-- =============================================================

INSERT INTO permissions (permission_id, name, description, app_path, app_icon, app_group, parent_name)
VALUES (
    '1000000010',
    'sign-hub',
    'Trung tâm ký duyệt văn bản HRM',
    '/sign-hub',
    'bi bi-pen-fill',
    'hrm',
    'offboarding'
)
ON CONFLICT (permission_id) DO UPDATE SET
    name        = EXCLUDED.name,
    description = EXCLUDED.description,
    app_path    = EXCLUDED.app_path,
    app_icon    = EXCLUDED.app_icon,
    app_group   = EXCLUDED.app_group,
    parent_name = EXCLUDED.parent_name;

-- Add sign-hub for superAdmin and admin if missing
UPDATE roles
SET permissions = array_append(permissions, '1000000010')
WHERE role_id IN ('2000000001', '2000000002')
  AND NOT ('1000000010' = ANY(permissions));

SELECT 'Migration sign-hub permission completed.' AS status;
