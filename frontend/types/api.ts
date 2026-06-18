export type Account = {
  id: number;
  email: string;
  role: string;
};

export type Session = {
  account: Account | null;
  has_admin: boolean;
  enable_writes: boolean;
  enable_email: boolean;
};

export type Lookup = {
  id: number;
  name?: string;
  suite_number?: string;
  status?: string;
};

export type AccessRequest = {
  id: number;
  request_type: string;
  status: string;
  requested_for_first_name: string;
  requested_for_last_name: string;
  requested_for_email: string;
  requested_for_company_text?: string | null;
  requested_for_suite_text?: string | null;
  requested_for_department?: string | null;
  reason?: string | null;
  created_at: string;
};

export type User = {
  id: number;
  name: string;
  email: string;
  employee_number?: string | null;
  company?: Lookup | null;
  suite?: Lookup | null;
  access_profile?: Lookup | null;
  department?: string | null;
  status: string;
  last_verified_at?: string | null;
  desired_unifi_access_policy_names?: string[];
  desired_unifi_user_group_names?: string[];
  current_unifi_access_policy_names?: string[];
  current_unifi_user_group_names?: string[];
};

export type Company = Lookup & {
  legal_name?: string | null;
  primary_contact_email?: string | null;
  active_user_count: number;
  suite_count: number;
};

export type Suite = Lookup & {
  floor?: string | null;
  building_area?: string | null;
  assigned_company?: Lookup | null;
  active_user_count: number;
};

export type Occupancy = {
  id: number;
  company?: Lookup | null;
  suite?: Lookup | null;
  occupancy_status: string;
  active_user_count: number;
  start_date?: string | null;
  end_date?: string | null;
};

export type AccessProfile = Lookup & {
  description?: string | null;
  active: boolean;
  unifi_access_policy_ids: string[];
  unifi_user_group_ids: string[];
  assignment_count: number;
};

export type Conflict = {
  id: number;
  conflict_type: string;
  description: string;
  severity: "high" | "medium" | "low";
  status: string;
  created_at: string;
  resolved_at?: string | null;
};

export type SyncJob = {
  id: number;
  access_request_id?: number | null;
  job_type: string;
  status: string;
  attempt_count: number;
  last_error?: string | null;
  created_at: string;
  completed_at?: string | null;
};

export type ReportRun = {
  id: number;
  report_type: string;
  status: string;
  recipient_email?: string | null;
  created_at: string;
  sent_at?: string | null;
};

export type AuditLog = {
  id: number;
  actor_email?: string | null;
  action: string;
  target_type: string;
  target_id?: string | null;
  created_at: string;
};

export type DashboardData = {
  stats: Record<string, number>;
  recent_requests: AccessRequest[];
  recent_conflicts: Conflict[];
  recent_reports: ReportRun[];
  recent_sync_jobs: SyncJob[];
  analytics: {
    sync_activity: Array<{ label: string; value: number }>;
    conflict_summary: Array<{ label: string; value: number }>;
    verification_status: Array<{ label: string; value: number }>;
  };
};
