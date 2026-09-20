import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { CallSession, LiveCallEvent, TranscriptTurn, CallLifecycle } from '../types';

export type ConnectionState = 'connected' | 'connecting' | 'reconnecting' | 'disconnected';

export interface UseLiveCallMonitorOptions {
  activeCallsProp?: CallSession[];
  allCallsProp?: CallSession[];
  onRefreshData?: () => void;
}

export function useLiveCallMonitor(options: UseLiveCallMonitorOptions = {}) {
  const { activeCallsProp = [], allCallsProp = [], onRefreshData } = options;

  // Authoritative live calls map: Record<callId, CallSession>
  const [liveCallsMap, setLiveCallsMap] = useState<Record<string, CallSession>>({});

  // Call-scoped transcripts: Record<callId, TranscriptTurn[]> (Constraint 5)
  const [transcriptsByCall, setTranscriptsByCall] = useState<Record<string, TranscriptTurn[]>>({});

  // Selected Call ID for inspection
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);

  // WebSocket connection state (Constraint 4)
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');

  // Operation loading flags
  const [isHangingUp, setIsHangingUp] = useState<string | null>(null);
  const [isCleaningStale, setIsCleaningStale] = useState(false);

  // Monotonic 1-second clock for zero-freeze duration calculation
  const [nowMs, setNowMs] = useState<number>(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Constraint 3: Idempotency and Monotonic Sequence Trackers
  const lastSequenceByCall = useRef<Record<string, number>>({});
  const processedEventIds = useRef<Set<string>>(new Set());

  // Constraint 4: Reconnect Resynchronization via REST API
  const resynchronizeActiveCalls = useCallback(async () => {
    try {
      const resp = await fetch('/api/v1/calls/active');
      if (!resp.ok) return;
      const activeList: CallSession[] = await resp.json();

      setLiveCallsMap(prev => {
        const nextMap: Record<string, CallSession> = {};
        activeList.forEach(call => {
          nextMap[call.id] = {
            ...call,
            handler: call.handler || {
              type: (call.handled_by_user_id ? 'HUMAN' : 'AI') as any,
              name: call.handled_by_name || call.agent_name || 'Superfone AI Ananya',
              role: call.handled_by_user_id ? 'Human Agent' : 'AI Receptionist'
            },
            media: call.media || {
              rtp: 'RECEIVING',
              codec: 'G.711 PCMU',
              sample_rate: 8000
            },
            vad_state: (call.vad_state as any) || 'LISTENING'
          };

          // Also populate call-scoped DB transcripts if not already present
          if (call.transcript && Array.isArray(call.transcript) && call.transcript.length > 0) {
            setTranscriptsByCall(tPrev => {
              if (tPrev[call.id] && tPrev[call.id].length >= call.transcript.length) {
                return tPrev;
              }
              const turns: TranscriptTurn[] = call.transcript.map((t, idx) => ({
                id: t.id || `${call.id}-${idx}`,
                call_id: call.id,
                speaker: (t.speaker || (t.role === 'user' ? 'USER' : 'AI')) as any,
                role: t.role || (t.speaker === 'USER' ? 'user' : 'assistant'),
                text: t.content || (t as any).text || '',
                timestamp: t.timestamp || call.started_at || new Date().toISOString(),
                partial: false,
                audio_dur_s: t.audio_dur_s,
                wav_file: t.wav_file
              }));
              return { ...tPrev, [call.id]: turns };
            });
          }
        });
        return nextMap;
      });

      if (onRefreshData) onRefreshData();
    } catch (err) {
      console.error('Failed to resynchronize active calls:', err);
    }
  }, [onRefreshData]);

  // Sync props activeCalls into liveCallsMap safely
  useEffect(() => {
    if (!activeCallsProp || activeCallsProp.length === 0) return;
    setLiveCallsMap(prev => {
      const next = { ...prev };
      activeCallsProp.forEach(call => {
        if (call.status !== 'completed' && call.status !== 'ENDED') {
          next[call.id] = {
            ...call,
            handler: call.handler || {
              type: (call.handled_by_user_id ? 'HUMAN' : 'AI') as any,
              name: call.handled_by_name || call.agent_name || 'Superfone AI Ananya',
              role: call.handled_by_user_id ? 'Human Agent' : 'AI Receptionist'
            },
            media: call.media || {
              rtp: 'RECEIVING',
              codec: 'G.711 PCMU',
              sample_rate: 8000
            },
            vad_state: (call.vad_state as any) || 'LISTENING'
          };
        }
      });
      return next;
    });
  }, [activeCallsProp]);

  // Real-Time Telephony WebSocket connection with Idempotency & Auto-Reconnect
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: any = null;
    let isMounted = true;

    const connectWs = () => {
      if (!isMounted) return;
      setConnectionState(prev => (prev === 'connected' ? 'reconnecting' : 'connecting'));

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/live`;

      try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          if (!isMounted) return;
          console.log('📡 [useLiveCallMonitor] WebSocket Connected -> Triggering Resync (Constraint 4)');
          setConnectionState('connected');
          // Constraint 4: Immediately resynchronize live calls on connect/reconnect
          resynchronizeActiveCalls();
        };

        ws.onmessage = (event) => {
          try {
            const data: LiveCallEvent = JSON.parse(event.data);
            const evtType = data.event || data.event_type || '';
            const cid = data.call_id || (data.payload?.call_id as string);
            const evtId = data.event_id;
            const seq = data.sequence;

            // Constraint 3: Deduplication check
            if (evtId && processedEventIds.current.has(evtId)) {
              return;
            }
            if (evtId) {
              processedEventIds.current.add(evtId);
              // Cap processed set to prevent memory growth
              if (processedEventIds.current.size > 2000) {
                const arr = Array.from(processedEventIds.current);
                processedEventIds.current = new Set(arr.slice(1000));
              }
            }

            // Constraint 3: Per-call Monotonic Sequence Check
            if (cid && typeof seq === 'number') {
              const lastSeq = lastSequenceByCall.current[cid] || 0;
              if (seq <= lastSeq) {
                console.warn(`[useLiveCallMonitor] Dropping out-of-order event seq ${seq} <= ${lastSeq} for call ${cid}`);
                return;
              }
              lastSequenceByCall.current[cid] = seq;
            }

            // 1. Authoritative CALL_CONNECTED / CALL_CREATED
            if ((evtType === 'CALL_CONNECTED' || evtType === 'CALL_CREATED') && cid) {
              setLiveCallsMap(prev => ({
                ...prev,
                [cid]: {
                  id: cid,
                  organization_id: 'default',
                  provider: 'microsip_direct',
                  direction: 'outbound',
                  from_number: data.payload?.from_number || '+918000000700',
                  to_number: data.payload?.to_number || 'MicroSIP Softphone',
                  status: 'CONNECTED',
                  started_at: data.timestamp || new Date().toISOString(),
                  duration_s: 0,
                  transcript: [],
                  created_at: data.timestamp || new Date().toISOString(),
                  interactions: [],
                  handler: data.payload?.handler || {
                    type: 'AI',
                    name: 'Ananya AI Receptionist',
                    role: 'AI Voice Agent'
                  },
                  media: {
                    rtp: 'RECEIVING',
                    codec: 'G.711 PCMU',
                    sample_rate: 8000
                  },
                  vad_state: 'LISTENING'
                }
              }));
              setSelectedCallId(prev => prev || cid);
            }

            // 2. Authoritative CALL_ENDED (Instant softphone hangup detection)
            else if (evtType === 'CALL_ENDED') {
              console.log(`🛑 [useLiveCallMonitor] Call ended received for ${cid}`);
              if (cid) {
                setLiveCallsMap(prev => {
                  const next = { ...prev };
                  delete next[cid];
                  return next;
                });
              } else {
                setLiveCallsMap({});
              }
              if (onRefreshData) onRefreshData();
            }

            // 3. State change / Recovery Pending (Constraint 1 & 2)
            else if (evtType === 'CALL_STATE_CHANGED' && cid) {
              setLiveCallsMap(prev => {
                if (!prev[cid]) return prev;
                return {
                  ...prev,
                  [cid]: {
                    ...prev[cid],
                    status: (data.payload?.status as CallLifecycle) || prev[cid].status,
                    media: {
                      ...prev[cid].media,
                      rtp: (data.payload?.media_status as any) || prev[cid].media?.rtp || 'RECEIVING'
                    }
                  }
                };
              });
            }

            // 4. Handler Changed (e.g. Human Handoff)
            else if (evtType === 'CALL_HANDLER_CHANGED' && cid) {
              setLiveCallsMap(prev => {
                if (!prev[cid]) return prev;
                const newHandler = data.payload?.handler || prev[cid].handler;
                return {
                  ...prev,
                  [cid]: {
                    ...prev[cid],
                    handler: newHandler,
                    status: newHandler?.type === 'HUMAN' ? 'HUMAN_CONNECTED' : prev[cid].status
                  }
                };
              });
            }

            // 5. Media & VAD Status updates
            else if (evtType === 'MEDIA_STATUS' && cid) {
              setLiveCallsMap(prev => {
                if (!prev[cid]) return prev;
                return {
                  ...prev,
                  [cid]: {
                    ...prev[cid],
                    media: {
                      ...prev[cid].media,
                      rtp: (data.payload?.rtp as any) || prev[cid].media?.rtp || 'RECEIVING',
                      last_packet_at: data.timestamp
                    }
                  }
                };
              });
            }

            // 6. Constraint 5: Call-Scoped Speech Transcription (Partial or Final)
            else if (
              evtType === 'TRANSCRIPT_PARTIAL' ||
              evtType === 'TRANSCRIPT_FINAL' ||
              evtType === 'USER_UTTERANCE' ||
              evtType === 'AI_RESPONSE'
            ) {
              const speaker = data.payload?.speaker || (evtType === 'USER_UTTERANCE' ? 'USER' : 'AI');
              const text = data.payload?.text || '';
              const isPartial = evtType === 'TRANSCRIPT_PARTIAL' || !!data.payload?.partial;
              const targetCallId = cid || selectedCallId || 'live';
              const turnId = data.payload?.turn_id || `${targetCallId}-${speaker.toLowerCase()}-${Date.now()}`;

              if (text) {
                setTranscriptsByCall(prev => {
                  const existingTurns = prev[targetCallId] ? [...prev[targetCallId]] : [];

                  // Check if there is an active partial turn for this speaker that we can update in-place
                  const lastTurnIndex = existingTurns.length - 1;
                  if (
                    lastTurnIndex >= 0 &&
                    existingTurns[lastTurnIndex].speaker === speaker &&
                    existingTurns[lastTurnIndex].partial
                  ) {
                    if (isPartial) {
                      existingTurns[lastTurnIndex] = {
                        ...existingTurns[lastTurnIndex],
                        text,
                        timestamp: data.timestamp || existingTurns[lastTurnIndex].timestamp
                      };
                    } else {
                      // Promoted to final!
                      existingTurns[lastTurnIndex] = {
                        ...existingTurns[lastTurnIndex],
                        id: turnId,
                        text,
                        partial: false,
                        audio_dur_s: data.payload?.audio_dur_s,
                        wav_file: data.payload?.wav_file,
                        timestamp: data.timestamp || existingTurns[lastTurnIndex].timestamp
                      };
                    }
                  } else {
                    // Append new turn
                    existingTurns.push({
                      id: turnId,
                      event_id: evtId,
                      call_id: targetCallId,
                      speaker: speaker as any,
                      role: speaker === 'USER' ? 'user' : 'assistant',
                      text,
                      timestamp: data.timestamp || new Date().toISOString(),
                      partial: isPartial,
                      audio_dur_s: data.payload?.audio_dur_s,
                      wav_file: data.payload?.wav_file
                    });
                  }

                  return {
                    ...prev,
                    [targetCallId]: existingTurns
                  };
                });
              }
            }
          } catch (err) {
            console.error('Error handling WebSocket message:', err);
          }
        };

        ws.onclose = () => {
          if (!isMounted) return;
          setConnectionState('disconnected');
          reconnectTimeout = setTimeout(connectWs, 2500);
        };

        ws.onerror = () => {
          if (ws) ws.close();
        };
      } catch (e) {
        if (isMounted) {
          setConnectionState('disconnected');
          reconnectTimeout = setTimeout(connectWs, 3000);
        }
      }
    };

    connectWs();

    return () => {
      isMounted = false;
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [resynchronizeActiveCalls, onRefreshData, selectedCallId]);

  // Periodic 5s background reconciliation
  useEffect(() => {
    const interval = setInterval(resynchronizeActiveCalls, 5000);
    return () => clearInterval(interval);
  }, [resynchronizeActiveCalls]);

  // List of active calls derived from liveCallsMap
  const activeCallsList = useMemo(() => {
    return Object.values(liveCallsMap).filter(
      c => c.status !== 'completed' && c.status !== 'ENDED'
    );
  }, [liveCallsMap]);

  // Default selection to first active call or latest call
  useEffect(() => {
    if (!selectedCallId && activeCallsList.length > 0) {
      setSelectedCallId(activeCallsList[0].id);
    } else if (!selectedCallId && allCallsProp.length > 0) {
      setSelectedCallId(allCallsProp[0].id);
    }
  }, [activeCallsList, allCallsProp, selectedCallId]);

  // Selected Call object
  const selectedCall = useMemo(() => {
    if (!selectedCallId) return null;
    return liveCallsMap[selectedCallId] || allCallsProp.find(c => c.id === selectedCallId) || null;
  }, [liveCallsMap, allCallsProp, selectedCallId]);

  // Call-Scoped turns for the selected call (Constraint 5)
  const selectedCallTranscripts = useMemo(() => {
    if (!selectedCallId) return [];
    return transcriptsByCall[selectedCallId] || [];
  }, [transcriptsByCall, selectedCallId]);

  // Formatter: Dynamic Live Duration
  const getCallDuration = useCallback(
    (call: CallSession) => {
      if (!call.started_at) return `${call.duration_s || 0}s`;
      const start = new Date(call.started_at).getTime();
      const end = call.ended_at ? new Date(call.ended_at).getTime() : nowMs;
      const diffSec = Math.max(0, Math.floor((end - start) / 1000));
      const mins = Math.floor(diffSec / 60);
      const secs = diffSec % 60;
      return `${mins > 0 ? `${mins}m ` : ''}${secs}s`;
    },
    [nowMs]
  );

  // Hang up action
  const hangupCall = useCallback(async (callId: string) => {
    setIsHangingUp(callId);
    try {
      const resp = await fetch(`/api/v1/calls/${callId}/hangup`, { method: 'POST' });
      if (resp.ok) {
        setLiveCallsMap(prev => {
          const next = { ...prev };
          delete next[callId];
          return next;
        });
        if (onRefreshData) onRefreshData();
      } else {
        alert('Failed to terminate call session');
      }
    } catch (err: any) {
      alert(`Error hanging up: ${err.message}`);
    } finally {
      setIsHangingUp(null);
    }
  }, [onRefreshData]);

  // Purge Stale Calls Action
  const purgeStaleCalls = useCallback(async () => {
    setIsCleaningStale(true);
    try {
      const resp = await fetch('/api/v1/calls/cleanup-stale', { method: 'POST' });
      const data = await resp.json();
      setLiveCallsMap({});
      if (onRefreshData) onRefreshData();
      alert(`Purged ${data.cleaned_count || 0} stale dead call session(s)!`);
    } catch (err: any) {
      alert(`Error cleaning stale calls: ${err.message}`);
    } finally {
      setIsCleaningStale(false);
    }
  }, [onRefreshData]);

  // Telemetry metrics calculation
  const metrics = useMemo(() => {
    const aiCount = activeCallsList.filter(c => !c.handler || c.handler.type === 'AI').length;
    const humanCount = activeCallsList.filter(c => c.handler?.type === 'HUMAN').length;
    const transferringCount = activeCallsList.filter(c => c.handler?.type === 'TRANSFERRING').length;
    const totalTurns = Object.values(transcriptsByCall).reduce((sum, list) => sum + list.length, 0);

    return {
      activeCount: activeCallsList.length,
      aiCount,
      humanCount,
      transferringCount,
      totalTurns
    };
  }, [activeCallsList, transcriptsByCall]);

  return {
    calls: activeCallsList,
    liveCallsMap,
    transcriptsByCall,
    selectedCall,
    selectedCallId,
    selectedCallTranscripts,
    connectionState,
    metrics,
    isHangingUp,
    isCleaningStale,
    selectCall: setSelectedCallId,
    hangupCall,
    purgeStaleCalls,
    getCallDuration,
    resynchronizeActiveCalls
  };
}
