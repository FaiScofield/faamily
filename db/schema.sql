begin;

create extension if not exists pgcrypto;

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  status smallint not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_users_status on users(status);

create table if not exists user_identities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  type text not null,
  identifier text not null,
  provider text null,
  verified_at timestamptz null,
  extra jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_user_identities_type check (type in ('wechat', 'phone', 'email')),
  constraint uq_user_identities_type_identifier unique (type, identifier)
);

create index if not exists idx_user_identities_user_id on user_identities(user_id);
create index if not exists idx_user_identities_type on user_identities(type);

create table if not exists families (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  avatar_url text null,
  owner_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_families_owner_user_id on families(owner_user_id);

create table if not exists memberships (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  role text not null,
  status text not null default 'active',
  display_name text null,
  joined_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_memberships_role check (role in ('owner', 'admin', 'member', 'child')),
  constraint chk_memberships_status check (status in ('active', 'pending', 'removed')),
  constraint uq_memberships_family_user unique (family_id, user_id)
);

create index if not exists idx_memberships_family_role on memberships(family_id, role);
create index if not exists idx_memberships_user_id on memberships(user_id);

create table if not exists invites (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  code text not null,
  expires_at timestamptz not null,
  max_uses int not null default 1,
  used_count int not null default 0,
  need_approval boolean not null default false,
  created_by_user_id uuid not null references users(id),
  disabled_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_invites_code unique (code),
  constraint chk_invites_max_uses check (max_uses >= 1),
  constraint chk_invites_used_count check (used_count >= 0)
);

create index if not exists idx_invites_family_expires on invites(family_id, expires_at);

create table if not exists announcements (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  title text not null,
  content text not null,
  pinned boolean not null default false,
  created_by_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz null
);

create index if not exists idx_announcements_family_created on announcements(family_id, created_at desc);
create index if not exists idx_announcements_family_pinned on announcements(family_id, pinned);

create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  title text not null,
  description text null,
  created_by_user_id uuid not null references users(id),
  assignee_user_id uuid null references users(id),
  reviewer_user_id uuid null references users(id),
  due_at timestamptz null,
  priority smallint not null default 0,
  status text not null default 'pending',
  repeat_rule jsonb null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz null,
  constraint chk_tasks_status check (status in ('pending', 'in_progress', 'submitted', 'done', 'rejected'))
);

create index if not exists idx_tasks_family_status_due on tasks(family_id, status, due_at);
create index if not exists idx_tasks_family_assignee_status on tasks(family_id, assignee_user_id, status);
create index if not exists idx_tasks_family_created on tasks(family_id, created_at desc);

create table if not exists task_submissions (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  task_id uuid not null references tasks(id) on delete cascade,
  submitted_by_user_id uuid not null references users(id),
  note text null,
  status text not null default 'submitted',
  review_note text null,
  created_at timestamptz not null default now(),
  constraint chk_task_submissions_status check (status in ('submitted', 'approved', 'rejected'))
);

create index if not exists idx_task_submissions_task_created on task_submissions(task_id, created_at desc);

create table if not exists folders (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  zone text not null,
  name text not null,
  parent_id uuid null references folders(id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_folders_zone check (zone in ('shared', 'vault'))
);

create unique index if not exists uq_folders_family_zone_parent_name
  on folders(family_id, zone, coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), name);

create index if not exists idx_folders_family_zone on folders(family_id, zone);

create table if not exists files (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  zone text not null,
  folder_id uuid null references folders(id) on delete set null,
  owner_type text not null,
  owner_id uuid null,
  uploader_user_id uuid not null references users(id),
  filename text not null,
  mime_type text not null,
  size_bytes bigint not null default 0,
  storage_key text not null,
  checksum text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz null,
  constraint chk_files_zone check (zone in ('shared', 'vault', 'attachment')),
  constraint chk_files_owner_type check (owner_type in ('document', 'announcement', 'task_submission')),
  constraint uq_files_storage_key unique (storage_key),
  constraint chk_files_size_bytes check (size_bytes >= 0)
);

create index if not exists idx_files_family_zone_folder_created on files(family_id, zone, folder_id, created_at desc);
create index if not exists idx_files_owner on files(owner_type, owner_id);

create table if not exists quotas (
  family_id uuid primary key references families(id) on delete cascade,
  plan text not null default 'free',
  total_bytes bigint not null default 2147483648,
  used_bytes bigint not null default 0,
  updated_at timestamptz not null default now(),
  constraint chk_quotas_total_bytes check (total_bytes >= 0),
  constraint chk_quotas_used_bytes check (used_bytes >= 0)
);

create table if not exists vault_email_otps (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  email text not null,
  code_hash text not null,
  expires_at timestamptz not null,
  consumed_at timestamptz null,
  created_at timestamptz not null default now()
);

create index if not exists idx_vault_email_otps_user_expires on vault_email_otps(user_id, expires_at desc);

create table if not exists vault_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  family_id uuid not null references families(id) on delete cascade,
  issued_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz null
);

create index if not exists idx_vault_sessions_user_family_expires on vault_sessions(user_id, family_id, expires_at desc);

create table if not exists scenario_templates (
  id uuid primary key default gen_random_uuid(),
  key text not null,
  name text not null,
  version int not null default 1,
  definition jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_scenario_templates_key_version unique (key, version)
);

create table if not exists scenario_instances (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  template_id uuid not null references scenario_templates(id),
  status text not null default 'enabled',
  config jsonb not null default '{}'::jsonb,
  enabled_at timestamptz not null default now(),
  constraint chk_scenario_instances_status check (status in ('enabled', 'disabled'))
);

create unique index if not exists uq_scenario_instances_family_template on scenario_instances(family_id, template_id);

create table if not exists audit_logs (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(id) on delete cascade,
  actor_user_id uuid not null references users(id),
  action text not null,
  target_type text null,
  target_id uuid null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_audit_logs_family_created on audit_logs(family_id, created_at desc);
create index if not exists idx_audit_logs_action on audit_logs(action);

commit;
