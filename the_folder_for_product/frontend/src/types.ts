export interface ServiceHealth {
  name: string;
  port: number;
  url: string;
  status: 'healthy' | 'degraded' | 'offline';
  latency_ms?: number;
}

export interface SystemOverview {
  total_calls: number;
  active_calls: number;
  completed_calls: number;
  human_handoffs: number;
  total_contacts: number;
  overall_pass_rate: number;
  services: ServiceHealth[];
}

export interface Contact {
  id: string;
  organization_id: string;
  phone_number: string;
  name?: string;
  email?: string;
  status: string;
  preferred_language: string;
  lead_source?: string;
  lead_owner_id?: string;
  lead_owner_name?: string;
  custom_fields?: Record<string, any>;
  last_called_at?: string;
  created_at: string;
  updated_at: string;
}

export interface TeamMember {
  id: string;
  name: string;
  email?: string;
  phone?: string;
  role: string;
  is_active: boolean;
  assigned_leads_count: number;
  created_at: string;
}

export interface LeadTask {
  id: string;
  title: string;
  description?: string;
  status: 'pending' | 'completed' | 'cancelled';
  due_at?: string;
  created_at: string;
  contact_id?: string;
  contact_name?: string;
  contact_phone?: string;
  lead_source?: string;
  assigned_to_id?: string;
  assigned_to_name?: string;
  custom_inquiry_data?: Record<string, any>;
}

export interface LeadReminder {
  id: string;
  note: string;
  remind_at: string;
  is_triggered: boolean;
  contact_name?: string;
  contact_phone?: string;
  created_at: string;
}

export interface WhatsAppMessage {
  id: string;
  direction: 'inbound' | 'outbound';
  message_text: string;
  status: string;
  timestamp: string;
}

export interface WhatsAppChat {
  phone_number: string;
  contact_name: string;
  contact_id?: string;
  messages: WhatsAppMessage[];
}

export interface TeamStats {
  id: string;
  name: string;
  email?: string;
  phone?: string;
  role: string;
  is_active: boolean;
  assigned_leads: number;
  total_calls: number;
  incoming_calls: number;
  outgoing_calls: number;
  total_talk_time_s: number;
  completed_tasks: number;
  daily_target?: number;
  target_progress_pct?: number;
}

export interface AgentProgressDetails {
  id: string;
  name: string;
  email: string;
  phone: string;
  role: string;
  is_active: boolean;
  created_at: string;
  metrics: {
    assigned_leads: number;
    total_calls: number;
    incoming_calls: number;
    outgoing_calls: number;
    total_talk_time_s: number;
    completed_tasks_count: number;
    pending_tasks_count: number;
    daily_target: number;
    target_progress_pct: number;
    qa_score: number;
    conversion_rate: number;
    script_adherence_pct: number;
    avg_call_duration_s: number;
  };
  recent_calls: Array<{
    id: string;
    from_number: string;
    to_number: string;
    duration_s: number;
    status: string;
    direction: string;
    created_at: string;
    intent?: string;
  }>;
  assigned_tasks: Array<{
    id: string;
    title: string;
    status: string;
    due_at?: string;
  }>;
  assigned_contacts: Array<{
    id: string;
    name: string;
    phone_number: string;
    status: string;
    lead_source?: string;
  }>;
}

export interface CallInteraction {
  id: string;
  call_id: string;
  intent_detected?: string;
  confidence?: number;
  ai_summary?: string;
  human_handoff_requested: boolean;
  followup_required: boolean;
  created_at: string;
}

export type CallLifecycle =
  | 'CALL_CREATED'
  | 'RINGING'
  | 'CONNECTED'
  | 'WAITING_FOR_AGENT'
  | 'AGENT_ACCEPTED'
  | 'BRIDGING'
  | 'HUMAN_CONNECTED'
  | 'RECOVERY_PENDING'
  | 'ON_HOLD'
  | 'ENDING'
  | 'ENDED'
  | 'COMPLETED'
  | 'FAILED'
  | 'in_progress'
  | 'completed';

export type CallHandlerType = 'AI' | 'HUMAN' | 'TRANSFERRING' | 'UNKNOWN';

export interface CallHandler {
  type: CallHandlerType;
  id?: string;
  name?: string;
  role?: string;
}

export type MediaHealthState = 'RECEIVING' | 'SENDING' | 'DEGRADED' | 'INACTIVE' | 'DISCONNECTED' | 'CONNECTED' | 'SILENT';
export type VadState = 'IDLE' | 'LISTENING' | 'SPEAKING' | 'UNKNOWN';

export interface CallMediaState {
  rtp: MediaHealthState;
  last_packet_at?: string;
  packets_received?: number;
  codec?: string;
  sample_rate?: number;
}

export interface TranscriptTurn {
  id: string;
  event_id?: string;
  call_id: string;
  speaker: 'USER' | 'AI' | 'HUMAN_AGENT';
  role?: string;
  text: string;
  timestamp: string;
  partial: boolean;
  confidence?: number;
  audio_dur_s?: number;
  wav_file?: string;
}

export interface LiveCallEvent {
  event_id: string;
  event: string;
  event_type?: string;
  call_id: string;
  timestamp: string;
  sequence?: number;
  payload?: Record<string, any>;
  raw?: string;
}

export interface CallSession {
  id: string;
  organization_id: string;
  contact_id?: string;
  provider: string;
  direction: string;
  from_number: string;
  to_number: string;
  status: string;
  started_at?: string;
  connected_at?: string;
  ended_at?: string;
  duration_s: number;
  recording_url?: string;
  transcript: {
    id?: string;
    role: string;
    content: string;
    speaker?: string;
    audio_dur_s?: number;
    wav_file?: string;
    timestamp?: string;
    partial?: boolean;
    turn_id?: string;
  }[];
  created_at: string;
  contact?: Contact;
  interactions: CallInteraction[];

  // Authoritative Handler & Media Telemetry
  handler?: CallHandler;
  media?: CallMediaState;
  vad_state?: 'SPEAKING' | 'LISTENING' | 'SILENT' | 'UNKNOWN';
  handled_by_user_id?: string;
  handled_by_name?: string;
  agent_name?: string;
  voice_model?: string;
  handoff_status?: string;
}

export interface Campaign {
  id: string;
  name: string;
  description?: string;
  type: 'SCRIPT' | 'AI' | 'HYBRID';
  status: 'DRAFT' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'FAILED';
  script_content?: string;
  voice_model: string;
  max_concurrency: number;
  calls_per_minute: number;
  max_retries: number;
  contact_count?: number;
  assigned_agent_id?: string;
  assigned_agent_name?: string;
  created_at: string;
  updated_at: string;
}

export interface CampaignContactDetail {
  id: string;
  contact_id: string;
  name: string;
  phone_number: string;
  email?: string;
  status: string;
  attempt_count: number;
  last_attempt_at?: string;
  final_outcome?: string;
}

export interface CampaignProgress {
  campaign_id: string;
  total_contacts: number;
  pending: number;
  queued: number;
  calling: number;
  answered: number;
  completed: number;
  no_answer: number;
  failed: number;
  progress_percentage: number;
}

export interface EvaluationReport {
  filename: string;
  run_id: string;
  timestamp: string;
  suite: string;
  transport: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  results_count: number;
}

export interface LoadTestSummary {
  filename: string;
  concurrency: number;
  total_elapsed_ms: number;
  total_calls: number;
  accepted: number;
  rejected: number;
  succeeded: number;
  stt_p50: number;
  stt_p95: number;
  llm_lock_p50: number;
  llm_lock_p95: number;
  tts_p50: number;
  tts_p95: number;
}

export interface LogEvent {
  timestamp: string;
  event_type: string;
  call_id: string;
  raw: string;
  payload: Record<string, any>;
}

export type AgentStatusType = 'available' | 'on_call' | 'in_break' | 'wrap_up' | 'offline';

export interface AgentProfile {
  id: string;
  name: string;
  email: string;
  phone: string;
  role: string;
  sip_extension: string;
  sip_password?: string;
  status: AgentStatusType;
  status_updated_at?: string;
  shift_name: string;
  daily_call_target: number;
  assigned_leads_count?: number;
  avatar_url?: string;
}

export interface AgentStats {
  calls_made_today: number;
  calls_target: number;
  talk_time_minutes: number;
  avg_handling_time_s: number;
  leads_converted: number;
  assigned_leads_count: number;
  pending_tasks_count: number;
  quality_score: number;
}

export interface AgentSession {
  token: string;
  agent: AgentProfile;
  stats: AgentStats;
}

export interface AgentContact {
  id: string;
  name: string;
  phone_number: string;
  email?: string;
  status: string;
  preferred_language: string;
  lead_source?: string;
  lead_owner_id?: string;
  last_called_at?: string;
  created_at: string;
  updated_at: string;
  total_calls: number;
  intent_score?: number;
  bot_summary?: string;
  last_intent?: string;
  last_disposition?: string;
  callback_scheduled_for?: string;
  agent_notes?: Array<{ text: string; timestamp: string; agent_id: string; disposition?: string }>;
  custom_fields?: Record<string, any>;
}

export interface AgentCallHistory {
  id: string;
  from_number: string;
  to_number: string;
  contact_id?: string;
  contact_name: string;
  contact_phone: string;
  direction: string;
  status: string;
  duration_s: number;
  recording_url?: string;
  transcript: Array<{ role: string; content: string }>;
  intent_detected?: string;
  ai_summary?: string;
  sentiment?: string;
  created_at?: string;
  started_at?: string;
  ended_at?: string;
}

