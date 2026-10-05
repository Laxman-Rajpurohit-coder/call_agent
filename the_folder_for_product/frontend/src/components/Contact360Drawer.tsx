import React, { useState, useEffect, useRef } from 'react';
import {
  X, Phone, PhoneCall, MessageSquare, Clock, Tag, UserCheck,
  Sparkles, CheckCircle2, AlertCircle, Play, Pause, ChevronDown,
  ChevronUp, Send, Calendar, Shield, Share2, Copy, Check, ArrowRight,
  RefreshCw, CornerDownRight, Volume2
} from 'lucide-react';
import { Contact, ContactTimelineData, ContactTimelineEvent } from '../types';

interface Contact360DrawerProps {
  contactId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onCallContact: (phone: string, name?: string) => void;
  onWhatsAppContact?: (phone: string, name?: string) => void;
  onContactUpdated?: () => void;
}

export const Contact360Drawer: React.FC<Contact360DrawerProps> = ({
  contactId,
  isOpen,
  onClose,
  onCallContact,
  onWhatsAppContact,
  onContactUpdated
}) => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ContactTimelineData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Note composer state
  const [noteText, setNoteText] = useState('');
  const [selectedDisposition, setSelectedDisposition] = useState<string>('Interested');
  const [remindMins, setRemindMins] = useState<number | null>(null);
  const [savingNote, setSavingNote] = useState(false);
  const [noteSuccess, setNoteSuccess] = useState(false);

  // Audio player state per call
  const [activeAudioUrl, setActiveAudioUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Expanded transcripts map
  const [expandedTranscripts, setExpandedTranscripts] = useState<Record<string, boolean>>({});

  // Tag manager state
  const [newTagInput, setNewTagInput] = useState('');
  const [isAddingTag, setIsAddingTag] = useState(false);
  const [copiedPhone, setCopiedPhone] = useState(false);

  // Fetch timeline data
  const fetchTimeline = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/contacts/${id}/timeline`);
      if (!res.ok) throw new Error('Failed to load contact timeline');
      const text = await res.text();
      const timelineData: ContactTimelineData = text ? JSON.parse(text) : null;
      if (timelineData) setData(timelineData);
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Error loading timeline');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && contactId) {
      fetchTimeline(contactId);
    } else {
      setData(null);
      if (audioRef.current) {
        audioRef.current.pause();
      }
      setIsPlaying(false);
      setActiveAudioUrl(null);
    }
  }, [isOpen, contactId]);

  if (!isOpen) return null;

  const handleCopyPhone = (phone: string) => {
    navigator.clipboard.writeText(phone);
    setCopiedPhone(true);
    setTimeout(() => setCopiedPhone(false), 2000);
  };

  const handleSaveNote = async () => {
    if (!contactId || !noteText.trim()) return;
    setSavingNote(true);
    try {
      const res = await fetch(`/api/v1/contacts/${contactId}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          note: noteText.trim(),
          disposition: selectedDisposition,
          remind_in_minutes: remindMins,
          sentiment: 'neutral'
        })
      });
      if (res.ok) {
        setNoteText('');
        setRemindMins(null);
        setNoteSuccess(true);
        setTimeout(() => setNoteSuccess(false), 2500);
        await fetchTimeline(contactId);
        if (onContactUpdated) onContactUpdated();
      }
    } catch (err) {
      console.error('Failed to save note:', err);
    } finally {
      setSavingNote(false);
    }
  };

  const handleToggleTag = async (tag: string, action: 'add' | 'remove') => {
    if (!contactId) return;
    try {
      const res = await fetch(`/api/v1/contacts/${contactId}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, tag })
      });
      if (res.ok) {
        await fetchTimeline(contactId);
        if (onContactUpdated) onContactUpdated();
      }
    } catch (err) {
      console.error('Failed to update tag:', err);
    }
  };

  const handleAddCustomTag = () => {
    if (!newTagInput.trim()) return;
    handleToggleTag(newTagInput.trim().toUpperCase(), 'add');
    setNewTagInput('');
    setIsAddingTag(false);
  };

  const toggleAudio = (url: string) => {
    if (activeAudioUrl === url && isPlaying) {
      audioRef.current?.pause();
      setIsPlaying(false);
    } else {
      setActiveAudioUrl(url);
      if (audioRef.current) {
        audioRef.current.src = url;
        audioRef.current.playbackRate = playbackSpeed;
        audioRef.current.play().catch(e => console.warn('Audio play error:', e));
        setIsPlaying(true);
      }
    }
  };

  const changeSpeed = (speed: number) => {
    setPlaybackSpeed(speed);
    if (audioRef.current) {
      audioRef.current.playbackRate = speed;
    }
  };

  const toggleTranscript = (eventId: string) => {
    setExpandedTranscripts(prev => ({
      ...prev,
      [eventId]: !prev[eventId]
    }));
  };

  const PRESET_TAGS = ['VIP', 'HOT LEAD', 'FOLLOW-UP', 'INTERESTED', 'NOT INTERESTED', 'EXISTING CUSTOMER'];
  const DISPOSITIONS = ['Interested', 'Callback Needed', 'Meeting Scheduled', 'Not Interested', 'Wrong Number', 'Left Voicemail'];

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-200">
      <audio
        ref={audioRef}
        onEnded={() => setIsPlaying(false)}
        onError={() => setIsPlaying(false)}
        className="hidden"
      />

      <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-2xl bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col h-full overflow-hidden text-slate-100">
          
          {/* Header */}
          <div className="p-5 border-b border-slate-800 bg-slate-900/95 sticky top-0 z-10 space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center space-x-3">
                  <h2 className="text-xl font-bold tracking-tight text-white">
                    {data?.name || 'Contact 360'}
                  </h2>
                  {data?.company && (
                    <span className="text-xs px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 font-medium">
                      {data.company}
                    </span>
                  )}
                  {data?.status && (
                    <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold uppercase tracking-wider bg-brand-500/10 text-brand-400 border border-brand-500/20">
                      {data.status}
                    </span>
                  )}
                </div>

                <div className="flex items-center space-x-2 text-sm text-slate-400 mt-1 font-mono">
                  <span>{data?.phone_number || ''}</span>
                  {data?.phone_number && (
                    <button
                      onClick={() => handleCopyPhone(data.phone_number)}
                      className="p-1 hover:text-white rounded hover:bg-slate-800 transition-colors"
                      title="Copy Phone"
                    >
                      {copiedPhone ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  )}
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => contactId && fetchTimeline(contactId)}
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                  title="Refresh Timeline"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-brand-400' : ''}`} />
                </button>
                <button
                  onClick={onClose}
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                  title="Close Drawer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Quick Action Bar */}
            <div className="flex items-center space-x-2 pt-1">
              <button
                onClick={() => data?.phone_number && onCallContact(data.phone_number, data.name)}
                className="flex-1 py-2 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center justify-center space-x-1.5 shadow-lg shadow-emerald-600/20 transition-all"
              >
                <PhoneCall className="w-3.5 h-3.5" />
                <span>Call Now</span>
              </button>

              <button
                onClick={() => {
                  if (onWhatsAppContact && data?.phone_number) {
                    onWhatsAppContact(data.phone_number, data.name);
                  } else if (data?.phone_number) {
                    const cleanPhone = data.phone_number.replace(/\+/g, '');
                    window.open(`https://wa.me/${cleanPhone}`, '_blank');
                  }
                }}
                className="flex-1 py-2 px-3 rounded-xl bg-teal-600/20 hover:bg-teal-600/30 text-teal-300 border border-teal-500/30 font-semibold text-xs flex items-center justify-center space-x-1.5 transition-all"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>WhatsApp</span>
              </button>

              <button
                onClick={() => {
                  const composer = document.getElementById('diary-note-composer');
                  composer?.scrollIntoView({ behavior: 'smooth' });
                }}
                className="py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs flex items-center space-x-1.5 border border-slate-700 transition-all"
              >
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                <span>Add Note</span>
              </button>
            </div>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {loading && !data && (
              <div className="py-20 flex flex-col items-center justify-center space-y-3 text-slate-400">
                <RefreshCw className="w-8 h-8 animate-spin text-brand-500" />
                <span className="text-sm">Building Contact 360 & Interaction Timeline...</span>
              </div>
            )}

            {error && (
              <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {data && (
              <>
                {/* 1. AI Customer Profile Card */}
                <div className="p-4 rounded-2xl bg-gradient-to-br from-brand-950/40 via-slate-900 to-slate-900 border border-brand-500/20 shadow-lg space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="p-1.5 rounded-lg bg-brand-500/20 text-brand-400 border border-brand-500/30">
                        <Sparkles className="w-4 h-4" />
                      </span>
                      <span className="font-semibold text-xs text-brand-300 tracking-wide uppercase">
                        AI Customer Summary
                      </span>
                    </div>

                    <div className="flex items-center space-x-2">
                      {data.ai_profile?.sentiment && (
                        <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${
                          data.ai_profile.sentiment.toLowerCase() === 'positive'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : data.ai_profile.sentiment.toLowerCase() === 'skeptical'
                            ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                            : 'bg-slate-800 text-slate-300 border-slate-700'
                        }`}>
                          {data.ai_profile.sentiment} Sentiment
                        </span>
                      )}
                      <span className="text-[10px] font-mono text-slate-500 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                        {data.ai_profile?.model || 'qwen3.8-27b'}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-slate-200 leading-relaxed font-sans">
                    {data.ai_profile?.summary || 'AI has not generated a conversation summary yet. Complete a call with Riya AI or add an agent note below.'}
                  </p>

                  {/* Intent Score Bar */}
                  {data.ai_profile?.intent_score !== undefined && (
                    <div className="space-y-1 pt-1">
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium">
                        <span>Lead Intent & Interest Score</span>
                        <span className="font-bold text-emerald-400">
                          {Math.round(data.ai_profile.intent_score * 100)}%
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-brand-500 to-emerald-400 rounded-full transition-all duration-500"
                          style={{ width: `${Math.min(100, Math.max(10, Math.round(data.ai_profile.intent_score * 100)))}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {data.ai_profile?.next_action && (
                    <div className="flex items-center space-x-2 text-[11px] bg-slate-950/60 p-2 rounded-xl border border-slate-800/80 text-brand-300">
                      <span className="font-semibold text-slate-400">Recommended Action:</span>
                      <span>{data.ai_profile.next_action}</span>
                    </div>
                  )}
                </div>

                {/* 2. Key Metrics Strip */}
                <div className="grid grid-cols-4 gap-2">
                  <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
                    <div className="text-lg font-bold text-white">{data.stats.total_calls}</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Total Calls</div>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
                    <div className="text-lg font-bold text-emerald-400">{data.stats.total_duration_s}s</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Talk Time</div>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
                    <div className="text-lg font-bold text-amber-400">{data.stats.total_notes}</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Notes</div>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
                    <div className="text-xs font-bold text-slate-300 truncate mt-1">
                      {data.stats.last_contacted_at ? new Date(data.stats.last_contacted_at).toLocaleDateString([], { month: 'short', day: 'numeric' }) : 'Never'}
                    </div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium mt-1">Last Touch</div>
                  </div>
                </div>

                {/* 3. Controlled Tags Manager */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
                    <span className="flex items-center space-x-1.5">
                      <Tag className="w-3.5 h-3.5 text-brand-400" />
                      <span>Contact Tags</span>
                    </span>
                    {!isAddingTag && (
                      <button
                        onClick={() => setIsAddingTag(true)}
                        className="text-[11px] text-brand-400 hover:text-brand-300 font-semibold"
                      >
                        + Add Custom Tag
                      </button>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-1.5 items-center">
                    {PRESET_TAGS.map(tag => {
                      const isActive = data.tags && data.tags.some(t => t.toUpperCase() === tag.toUpperCase());
                      return (
                        <button
                          key={tag}
                          onClick={() => handleToggleTag(tag, isActive ? 'remove' : 'add')}
                          className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                            isActive
                              ? 'bg-brand-600 text-white shadow-sm shadow-brand-600/30'
                              : 'bg-slate-800/80 text-slate-400 hover:text-slate-200 border border-slate-750'
                          }`}
                        >
                          {tag}
                        </button>
                      );
                    })}

                    {isAddingTag && (
                      <div className="flex items-center space-x-1 bg-slate-800 rounded-lg p-0.5 border border-slate-700">
                        <input
                          type="text"
                          value={newTagInput}
                          onChange={e => setNewTagInput(e.target.value)}
                          onKeyDown={e => e.key === 'Enter' && handleAddCustomTag()}
                          placeholder="TAG NAME..."
                          className="bg-transparent px-2 py-0.5 text-xs text-white uppercase focus:outline-none w-24"
                          autoFocus
                        />
                        <button
                          onClick={handleAddCustomTag}
                          className="p-1 bg-brand-600 hover:bg-brand-500 text-white rounded text-[10px] font-bold"
                        >
                          <Check className="w-3 h-3" />
                        </button>
                        <button
                          onClick={() => setIsAddingTag(false)}
                          className="p-1 hover:text-slate-300 rounded text-[10px]"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* 4. Note & Disposition Composer */}
                <div id="diary-note-composer" className="p-4 rounded-2xl bg-slate-950/80 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                    <span className="flex items-center space-x-1.5">
                      <Clock className="w-3.5 h-3.5 text-amber-400" />
                      <span>Post-Call Note & Disposition</span>
                    </span>
                    {noteSuccess && (
                      <span className="text-emerald-400 text-[11px] flex items-center space-x-1">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Saved to Diary!</span>
                      </span>
                    )}
                  </div>

                  <textarea
                    rows={2}
                    value={noteText}
                    onChange={e => setNoteText(e.target.value)}
                    placeholder="Enter interaction notes, customer objections, or key next steps..."
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-brand-500 resize-none"
                  />

                  {/* Disposition selection pills */}
                  <div className="space-y-1.5">
                    <div className="text-[10px] font-medium text-slate-400 uppercase tracking-wider">
                      Select Lead Disposition:
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {DISPOSITIONS.map(disp => (
                        <button
                          key={disp}
                          onClick={() => setSelectedDisposition(disp)}
                          className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                            selectedDisposition === disp
                              ? 'bg-amber-500 text-slate-950 font-bold shadow-md shadow-amber-500/20'
                              : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                          }`}
                        >
                          {disp}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Quick reminder triggers */}
                  <div className="flex items-center justify-between pt-1">
                    <div className="flex items-center space-x-1.5">
                      <span className="text-[10px] text-slate-400 font-medium">Remind:</span>
                      {[
                        { label: '+15m', mins: 15 },
                        { label: '+1h', mins: 60 },
                        { label: '+2h', mins: 120 },
                        { label: 'Tomorrow', mins: 1440 }
                      ].map(item => (
                        <button
                          key={item.mins}
                          onClick={() => setRemindMins(remindMins === item.mins ? null : item.mins)}
                          className={`px-2 py-0.5 rounded text-[10px] font-medium border ${
                            remindMins === item.mins
                              ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                              : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                          }`}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>

                    <button
                      onClick={handleSaveNote}
                      disabled={savingNote || !noteText.trim()}
                      className="px-4 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold flex items-center space-x-1.5 shadow-md shadow-brand-600/20 transition-all"
                    >
                      {savingNote ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                      <span>Save to Diary</span>
                    </button>
                  </div>
                </div>

                {/* 5. Unified Chronological Timeline */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                    <span>Interaction Timeline ({data.timeline.length} events)</span>
                    <span className="text-[10px] text-slate-500">Chronological • Newest First</span>
                  </div>

                  {data.timeline.length === 0 ? (
                    <div className="py-10 text-center text-slate-500 text-xs italic border border-dashed border-slate-800 rounded-2xl">
                      No interactions recorded for this contact yet.
                    </div>
                  ) : (
                    <div className="space-y-3 relative before:absolute before:inset-0 before:left-3.5 before:w-0.5 before:bg-slate-800/80">
                      {data.timeline.map((event) => {
                        const isCall = event.type === 'call';
                        const isNote = event.type === 'note';
                        const isReminder = event.type === 'reminder';
                        const isAudioPlaying = activeAudioUrl === event.recording_url && isPlaying;
                        const isTranscriptOpen = !!expandedTranscripts[event.id];

                        return (
                          <div key={event.id} className="relative pl-8 text-xs">
                            {/* Timeline Node Icon */}
                            <div className={`absolute left-1.5 top-2.5 w-4 h-4 rounded-full flex items-center justify-center -translate-x-1/2 border ${
                              isCall
                                ? 'bg-emerald-950 border-emerald-500 text-emerald-400'
                                : isNote
                                ? 'bg-amber-950 border-amber-500 text-amber-400'
                                : 'bg-cyan-950 border-cyan-500 text-cyan-400'
                            }`}>
                              <span className="w-1.5 h-1.5 rounded-full bg-current" />
                            </div>

                            {/* Event Card */}
                            <div className="p-4 rounded-2xl bg-slate-900/90 border border-slate-800 hover:border-slate-700/80 transition-all space-y-2.5">
                              {/* Event Header */}
                              <div className="flex items-center justify-between">
                                <div className="flex items-center space-x-2">
                                  <span className="font-semibold text-slate-200">
                                    {event.title}
                                  </span>
                                  {isCall && event.duration_s !== undefined && (
                                    <span className="text-[10px] font-mono text-slate-400 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">
                                      {event.duration_s}s
                                    </span>
                                  )}
                                  {isNote && event.disposition && (
                                    <span className="text-[10px] font-semibold text-amber-300 bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/20">
                                      {event.disposition}
                                    </span>
                                  )}
                                </div>

                                <div className="text-[10px] text-slate-500">
                                  {event.timestamp ? new Date(event.timestamp).toLocaleString([], {
                                    month: 'short',
                                    day: 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit'
                                  }) : ''}
                                </div>
                              </div>

                              {/* Handler Badge for Calls: AI vs Human Handoff */}
                              {isCall && event.handler && (
                                <div className="flex items-center space-x-2">
                                  {event.handler.transferred ? (
                                    <div className="flex items-center space-x-1.5 text-[10px] px-2 py-1 rounded-lg bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-medium">
                                      <CornerDownRight className="w-3 h-3 text-indigo-400" />
                                      <span>🤖 AI → 👤 Human Agent Transfer</span>
                                      {event.handler.reason && (
                                        <span className="text-indigo-400/80 italic">({event.handler.reason})</span>
                                      )}
                                    </div>
                                  ) : (
                                    <div className="flex items-center space-x-1.5 text-[10px] px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
                                      <span>🤖 Handled by Riya AI</span>
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* Note content */}
                              {isNote && (
                                <p className="text-slate-300 leading-relaxed font-sans text-xs bg-slate-950/40 p-2.5 rounded-xl border border-slate-800/60">
                                  {event.content}
                                </p>
                              )}

                              {/* Reminder details */}
                              {isReminder && (
                                <div className="text-slate-300 bg-slate-950/40 p-2.5 rounded-xl border border-slate-800/60 space-y-1">
                                  <div className="font-medium text-cyan-300">{event.content}</div>
                                  <div className="text-[10px] text-slate-500">
                                    Scheduled for: {event.remind_at ? new Date(event.remind_at).toLocaleString() : 'N/A'}
                                  </div>
                                </div>
                              )}

                              {/* Call Audio Player & Scrubbing */}
                              {isCall && event.recording_url && (
                                <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800/90 flex items-center justify-between space-x-3">
                                  <button
                                    onClick={() => toggleAudio(event.recording_url!)}
                                    className={`p-2 rounded-xl flex items-center justify-center transition-all ${
                                      isAudioPlaying
                                        ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/30'
                                        : 'bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 border border-emerald-500/30'
                                    }`}
                                    title={isAudioPlaying ? 'Pause Audio' : 'Play Call Recording'}
                                  >
                                    {isAudioPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                                  </button>

                                  <div className="flex-1 flex items-center space-x-2 text-[10px] text-slate-400 font-mono">
                                    <Volume2 className="w-3.5 h-3.5 text-slate-500" />
                                    <span>Call Recording ({event.duration_s || 0}s)</span>
                                  </div>

                                  {/* Speed selector */}
                                  <div className="flex items-center space-x-1">
                                    {[1, 1.25, 1.5, 2].map(speed => (
                                      <button
                                        key={speed}
                                        onClick={() => changeSpeed(speed)}
                                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                                          playbackSpeed === speed
                                            ? 'bg-slate-700 text-white font-bold'
                                            : 'text-slate-500 hover:text-slate-300'
                                        }`}
                                      >
                                        {speed}x
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Transcript Toggle & View */}
                              {isCall && event.transcript && event.transcript.length > 0 && (
                                <div className="space-y-2 pt-1 border-t border-slate-800/60">
                                  <button
                                    onClick={() => toggleTranscript(event.id)}
                                    className="flex items-center justify-between w-full text-[11px] font-semibold text-slate-400 hover:text-slate-200"
                                  >
                                    <span>Transcript Turns ({event.transcript.length})</span>
                                    {isTranscriptOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                                  </button>

                                  {isTranscriptOpen && (
                                    <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                                      {event.transcript.map((t, ti) => (
                                        <div
                                          key={ti}
                                          className={`p-2.5 rounded-xl border text-xs leading-relaxed ${
                                            t.role === 'user'
                                              ? 'bg-slate-800/70 border-slate-700/80 text-slate-200 ml-3'
                                              : 'bg-brand-600/10 border-brand-500/20 text-brand-200 mr-3'
                                          }`}
                                        >
                                          <div className="font-bold text-[9px] uppercase tracking-wider mb-1 flex items-center justify-between text-slate-400">
                                            <span>{t.role === 'user' ? '👤 Customer' : '🤖 Riya AI'}</span>
                                            {t.audio_dur_s && (
                                              <span className="font-mono text-emerald-400">{t.audio_dur_s}s</span>
                                            )}
                                          </div>
                                          <div>{t.content}</div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
