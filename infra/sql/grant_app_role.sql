-- Grant required privileges to the Cloud Run application DB role.
-- Run this script as a privileged/admin role in the target database.
--
-- Replace app_role_here with your application DB user/role (the one used by DATABASE_URL).

GRANT USAGE ON SCHEMA public TO app_role_here;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public
TO app_role_here;

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA public
TO app_role_here;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES TO app_role_here;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT, UPDATE
ON SEQUENCES TO app_role_here;
