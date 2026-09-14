import React, { useState } from 'react';
import { 
  Megaphone, Play, Pause, Plus, PhoneCall, CheckCircle2, Clock, Zap, 
  Mic, Users, Search, X, RefreshCw, Phone, Trash2, CheckSquare, Square, AlertTriangle
} from 'lucide-react';
import { Campaign, Contact, CampaignContactDetail } from '../types';

interface CampaignsPageProps {
  campaigns: Campaign[];
  contacts?: Contact[];
  onCreateCampaign: (campaign: any) => void;
  onStartCampaign: (id: string) => void;
  onPauseCampaign?: (id: string) => void;
  onResumeCampaign?: (id: string) => void;
  onStopCampaign?: (id: string) => void;
  onDeleteCampaign?: (id: string) => Promise<void> | void;
  onBulkDeleteCampaigns?: (ids: string[]) => Promise<void> | void;
}

export const CampaignsPage: React.FC<CampaignsPageProps> = ({
  campaigns,
  contacts = [],
  onCreateCampaign,
  onStartCampaign,
  onPauseCampaign,
  onResumeCampaign,
  onStopCampaign,
  onDeleteCampaign,
  onBulkDeleteCampaigns
}) => {
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState('');
  const [type, setType] = useState<'SCRIPT' | 'AI'>('SCRIPT');
  const [scriptContent, setScriptContent] = useState('');
  const [voiceModel, setVoiceModel] = useState('hi_pratham');
  const [concurrency, setConcurrency] = useState(5);

  // Audience & Contact Targeting States
  const [contactMode, setContactMode] = useState<'crm' | 'manual'>('crm');
  const [selectedContactIds, setSelectedContactIds] = useState<string[]>([]);
  const [manualNumbers, setManualNumbers] = useState('');
  const [includeSoftphone, setIncludeSoftphone] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Edit Campaign Script States
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null);
  const [editScript, setEditScript] = useState('');
  const [editVoice, setEditVoice] = useState('hi_pratham');

  // View Campaign Contacts States
  const [viewContactsCampaign, setViewContactsCampaign] = useState<Campaign | null>(null);
  const [campaignContacts, setCampaignContacts] = useState<CampaignContactDetail[]>([]);
  const [loadingContacts, setLoadingContacts] = useState(false);

  // Campaign Selection, Search & Deletion States
  const [selectedCampaignIds, setSelectedCampaignIds] = useState<string[]>([]);
  const [campaignSearch, setCampaignSearch] = useState<string>('');
  const [campaignToDelete, setCampaignToDelete] = useState<Campaign | null>(null);
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  // Filter Campaigns based on search query
  const filteredCampaignList = campaigns.filter(c => {
    if (!campaignSearch.trim()) return true;
    const q = campaignSearch.toLowerCase();
    const nameMatch = (c.name || '').toLowerCase().includes(q);
    const scriptMatch = (c.script_content || '').toLowerCase().includes(q);
    const voiceMatch = (c.voice_model || '').toLowerCase().includes(q);
    const statusMatch = (c.status || '').toLowerCase().includes(q);
    return nameMatch || scriptMatch || voiceMatch || statusMatch;
  });

  const handleToggleCampaign = (id: string) => {
    setSelectedCampaignIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSelectAllCampaigns = () => {
    const visibleIds = filteredCampaignList.map(c => c.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedCampaignIds.includes(id));
    if (allSelected) {
      setSelectedCampaignIds(prev => prev.filter(id => !visibleIds.includes(id)));
    } else {
      setSelectedCampaignIds(prev => Array.from(new Set([...prev, ...visibleIds])));
    }
  };

  const handleConfirmDeleteSingle = async () => {
    if (!campaignToDelete) return;
    setIsDeleting(true);
    try {
      if (onDeleteCampaign) {
        await onDeleteCampaign(campaignToDelete.id);
      } else {
        await fetch(`/api/v1/campaigns/${campaignToDelete.id}`, { method: 'DELETE' });
        window.location.reload();
      }
      setSelectedCampaignIds(prev => prev.filter(id => id !== campaignToDelete.id));
      setCampaignToDelete(null);
    } catch (e: any) {
      alert(`Failed to delete campaign: ${e.message}`);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleConfirmBulkDelete = async () => {
    if (selectedCampaignIds.length === 0) return;
    setIsDeleting(true);
    try {
      if (onBulkDeleteCampaigns) {
        await onBulkDeleteCampaigns(selectedCampaignIds);
      } else {
        await fetch('/api/v1/campaigns/bulk-delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ campaign_ids: selectedCampaignIds })
        });
        window.location.reload();
      }
      setSelectedCampaignIds([]);
      setShowBulkDeleteModal(false);
    } catch (e: any) {
      alert(`Failed to delete selected campaigns: ${e.message}`);
    } finally {
      setIsDeleting(false);
    }
  };

  // Filter CRM contacts based on search query
  const filteredContacts = contacts.filter(c => {
    const q = searchQuery.toLowerCase();
    const phone = (c.phone_number || '').toLowerCase();
    const cName = (c.name || '').toLowerCase();
    return phone.includes(q) || cName.includes(q);
  });

  const handleToggleContact = (id: string) => {
    setSelectedContactIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleToggleSelectAll = () => {
    const visibleIds = filteredContacts.map(c => c.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedContactIds.includes(id));
    if (allSelected) {
      setSelectedContactIds(prev => prev.filter(id => !visibleIds.includes(id)));
    } else {
      setSelectedContactIds(prev => Array.from(new Set([...prev, ...visibleIds])));
    }
  };

  const handleOpenContacts = async (c: Campaign) => {
    setViewContactsCampaign(c);
    setLoadingContacts(true);
    try {
      const resp = await fetch(`/api/v1/campaigns/${c.id}/contacts`);
      if (resp.ok) {
        const data = await resp.json();
        setCampaignContacts(data);
      } else {
        setCampaignContacts([]);
      }
    } catch (e) {
      console.error("Failed to load campaign contacts", e);
      setCampaignContacts([]);
    } finally {
      setLoadingContacts(false);
    }
  };

  const handleOpenEdit = (c: Campaign) => {
    setEditingCampaign(c);
    setEditScript(c.script_content || '');
    setEditVoice(c.voice_model || 'hi_pratham');
  };

  const handleSaveEdit = async () => {
    if (!editingCampaign) return;
    try {
      await fetch(`/api/v1/campaigns/${editingCampaign.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          script_content: editScript,
          voice_model: editVoice
        })
      });
      setEditingCampaign(null);
      window.location.reload();
    } catch (e) {
      alert("Failed to update campaign script.");
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Parse manual phone numbers
    const parsedManual = manualNumbers
      .split(/[\n,]+/)
      .map(s => s.trim())
      .filter(Boolean);

    let finalContactIds = [...selectedContactIds];
    if (includeSoftphone) {
      const softphone = contacts.find(c => c.phone_number?.includes('test1000') || c.phone_number?.includes('1000'));
      if (softphone && !finalContactIds.includes(softphone.id)) {
        finalContactIds.push(softphone.id);
      }
    }

    if (finalContactIds.length === 0 && parsedManual.length === 0 && !includeSoftphone) {
      alert("Please select at least one contact from CRM or enter a manual phone number.");
      return;
    }

    onCreateCampaign({
      name,
      type,
      script_content: scriptContent,
      max_concurrency: concurrency,
      voice_model: voiceModel,
      contact_ids: finalContactIds,
      custom_phone_numbers: parsedManual
    });

    setShowModal(false);
    setName('');
    setScriptContent('');
    setVoiceModel('hi_pratham');
    setSelectedContactIds([]);
    setManualNumbers('');
    setIncludeSoftphone(false);
    setSearchQuery('');
  };

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Top Banner */}
      <div className="glass-panel p-4 md:p-6 rounded-2xl border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg md:text-xl font-bold text-slate-100 flex items-center space-x-2">
            <Megaphone className="w-5 h-5 text-brand-500 shrink-0" />
            <span>Campaign & Auto Calling Engine</span>
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-1">Script-based & AI-driven batch outreach campaigns with queue concurrency manager.</p>
        </div>

        <button
          onClick={() => setShowModal(true)}
          className="flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium text-xs transition-colors shadow-lg shadow-brand-600/20 shrink-0"
        >
          <Plus className="w-4 h-4" />
          <span>New Campaign</span>
        </button>
      </div>

      {/* Search & Bulk Selection Toolbar */}
      <div className="glass-panel p-3.5 md:p-4 rounded-2xl border border-slate-800 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-2.5 flex-1 min-w-0">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search campaigns by name, script, voice..."
              value={campaignSearch}
              onChange={(e) => setCampaignSearch(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-7 py-2 text-slate-200 text-xs focus:outline-none focus:border-brand-500 transition-colors"
            />
            {campaignSearch && (
              <button
                type="button"
                onClick={() => setCampaignSearch('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={handleSelectAllCampaigns}
            className="flex items-center space-x-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-colors shrink-0"
            title="Toggle selection for all filtered campaigns"
          >
            {filteredCampaignList.length > 0 && filteredCampaignList.every(c => selectedCampaignIds.includes(c.id)) ? (
              <>
                <CheckSquare className="w-3.5 h-3.5 text-brand-400" />
                <span>Deselect All</span>
              </>
            ) : (
              <>
                <Square className="w-3.5 h-3.5 text-slate-400" />
                <span>Select All ({filteredCampaignList.length})</span>
              </>
            )}
          </button>
        </div>

        {/* Dynamic Bulk Action Bar when campaigns are selected */}
        {selectedCampaignIds.length > 0 ? (
          <div className="flex items-center space-x-2 bg-brand-500/10 border border-brand-500/30 px-3 py-1.5 rounded-xl shrink-0">
            <span className="text-xs font-semibold text-brand-300 flex items-center space-x-1.5">
              <CheckSquare className="w-3.5 h-3.5 text-brand-400" />
              <span>{selectedCampaignIds.length} Selected</span>
            </span>
            <div className="h-4 w-px bg-brand-500/30 mx-1"></div>
            <button
              type="button"
              onClick={() => setShowBulkDeleteModal(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs transition-colors shadow-md shadow-rose-600/30"
              title="Delete all selected campaigns"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Delete Selected ({selectedCampaignIds.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setSelectedCampaignIds([])}
              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded-lg hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="text-xs text-slate-400 hidden sm:block">
            Total Campaigns: <span className="font-semibold text-slate-200">{campaigns.length}</span>
          </div>
        )}
      </div>

      {/* Campaigns Grid */}
      {filteredCampaignList.length === 0 ? (
        <div className="glass-panel p-12 text-center rounded-2xl border border-slate-800 space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center mx-auto text-slate-500">
            <Megaphone className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-slate-200">
            {campaigns.length === 0 ? 'No campaigns created yet' : 'No matching campaigns found'}
          </h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            {campaigns.length === 0
              ? 'Click the "New Campaign" button above to launch an automated outreach campaign.'
              : `No campaigns matched "${campaignSearch}". Try refining your search query.`}
          </p>
          {campaignSearch && (
            <button
              type="button"
              onClick={() => setCampaignSearch('')}
              className="text-xs text-brand-400 hover:text-brand-300 underline font-medium"
            >
              Clear search filter
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
          {filteredCampaignList.map((c) => {
            const isSelected = selectedCampaignIds.includes(c.id);
            return (
              <div
                key={c.id}
                className={`glass-panel p-5 rounded-2xl border transition-all duration-200 space-y-4 flex flex-col justify-between ${
                  isSelected
                    ? 'border-brand-500/80 bg-brand-950/20 shadow-lg shadow-brand-500/10 ring-1 ring-brand-500/40'
                    : 'border-slate-800 hover:border-slate-700'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <button
                        type="button"
                        onClick={() => handleToggleCampaign(c.id)}
                        className={`w-5 h-5 rounded-md flex items-center justify-center border transition-all ${
                          isSelected
                            ? 'bg-brand-500 border-brand-500 text-white shadow-sm shadow-brand-500/30'
                            : 'bg-slate-900 border-slate-700 hover:border-slate-500 text-transparent'
                        }`}
                        title={isSelected ? "Deselect campaign" : "Select campaign"}
                      >
                        <CheckSquare className={`w-3.5 h-3.5 ${isSelected ? 'opacity-100' : 'opacity-0'}`} />
                      </button>
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${
                        c.status === 'RUNNING' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        c.status === 'COMPLETED' ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20' :
                        'bg-slate-800 text-slate-400'
                      }`}>
                        {c.status}
                      </span>
                    </div>
                    <span className="text-xs font-mono text-slate-500">{c.type} Mode</span>
                  </div>

                  <h3 className="text-base font-bold text-slate-100">{c.name}</h3>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2">{c.script_content || 'No custom script attached'}</p>
                </div>

                <div className="space-y-3 pt-3 border-t border-slate-800/80">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span className="flex items-center space-x-1">
                      <Mic className="w-3.5 h-3.5 text-brand-400" />
                      <span>Voice Model</span>
                    </span>
                    <span className="font-semibold text-brand-400 font-mono bg-brand-500/10 px-2 py-0.5 rounded border border-brand-500/20">
                      {c.voice_model || 'hi_pratham'}
                    </span>
                  </div>

                  <div className="flex justify-between text-xs text-slate-400">
                    <span className="flex items-center space-x-1">
                      <Users className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Target Audience</span>
                    </span>
                    <span className="font-semibold text-indigo-400 font-mono bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                      {c.contact_count ?? 1} contacts
                    </span>
                  </div>

                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Concurrency Limit</span>
                    <span className="font-semibold text-slate-200">{c.max_concurrency} workers</span>
                  </div>

                  <div className="flex items-center space-x-1.5 pt-1">
                    <button
                      type="button"
                      onClick={() => handleOpenContacts(c)}
                      className="flex-1 py-2 rounded-xl bg-slate-800/90 hover:bg-slate-700 text-slate-200 font-medium text-xs border border-slate-700 flex items-center justify-center space-x-1 transition-colors"
                      title="View contacts assigned to this campaign"
                    >
                      <Users className="w-3 h-3 text-slate-400" />
                      <span>Contacts</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleOpenEdit(c)}
                      className="flex-1 py-2 rounded-xl bg-slate-800/90 hover:bg-slate-700 text-slate-200 font-medium text-xs border border-slate-700 transition-colors"
                    >
                      ✏️ Edit
                    </button>

                    {c.status === 'RUNNING' ? (
                      <button
                        onClick={() => onPauseCampaign && onPauseCampaign(c.id)}
                        className="flex-1 flex items-center justify-center space-x-1 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-medium text-xs transition-colors shadow-lg shadow-amber-600/20"
                        title="Pause campaign execution"
                      >
                        <Pause className="w-3 h-3" />
                        <span>Pause</span>
                      </button>
                    ) : c.status === 'PAUSED' ? (
                      <button
                        onClick={() => onResumeCampaign && onResumeCampaign(c.id)}
                        className="flex-1 flex items-center justify-center space-x-1 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs transition-colors shadow-lg shadow-emerald-600/20"
                        title="Resume paused campaign"
                      >
                        <Play className="w-3 h-3" />
                        <span>Resume</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => onStartCampaign(c.id)}
                        className="flex-1 flex items-center justify-center space-x-1 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs transition-colors shadow-lg shadow-emerald-600/20"
                        title="Start dialing campaign contacts"
                      >
                        <Play className="w-3 h-3" />
                        <span>Start</span>
                      </button>
                    )}

                    {/* Single Campaign Delete Button */}
                    <button
                      type="button"
                      onClick={() => setCampaignToDelete(c)}
                      className="p-2 rounded-xl bg-slate-800/90 hover:bg-rose-950/50 text-slate-400 hover:text-rose-400 border border-slate-700 hover:border-rose-500/40 transition-all shrink-0"
                      title={`Delete campaign "${c.name}"`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 w-full max-w-lg space-y-4">
            <h3 className="text-lg font-bold text-slate-100">Create New Campaign</h3>
            
            <form onSubmit={handleSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Campaign Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Event Announcement Campaign"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Outreach Mode</label>
                  <select
                    value={type}
                    onChange={(e: any) => setType(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 text-sm"
                  >
                    <option value="SCRIPT">Script Calling (Predefined)</option>
                    <option value="AI">AI Agent Conversation</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1 flex items-center space-x-1">
                    <Mic className="w-3.5 h-3.5 text-brand-400" />
                    <span>Neural Voice Model</span>
                  </label>
                  <select
                    value={voiceModel}
                    onChange={(e) => setVoiceModel(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 text-sm"
                  >
                    <optgroup label="⚡ Cloud Ultra-Realistic Voices (Cartesia / Deepgram / ElevenLabs / OpenAI)">
                      <option value="cartesia_hi_sonic">⚡ Cartesia Cloud — Hindi Sonic (Ultra-Realistic & Low Latency)</option>
                      <option value="cartesia_hi_female">⚡ Cartesia Cloud — Hindi Female (hi-IN)</option>
                      <option value="cartesia_en_sonic">⚡ Cartesia Cloud — English Sonic (Ultra-Realistic)</option>
                      <option value="deepgram_aura_asteria">⚡ Deepgram Cloud — Aura Asteria (Female)</option>
                      <option value="deepgram_aura_orion">⚡ Deepgram Cloud — Aura Orion (Male)</option>
                      <option value="elevenlabs_multilingual">⚡ ElevenLabs Cloud — Multilingual Studio Voice</option>
                      <option value="openai_alloy">⚡ OpenAI Cloud — Alloy (Neutral)</option>
                      <option value="openai_echo">⚡ OpenAI Cloud — Echo (Male Clear)</option>
                      <option value="openai_nova">⚡ OpenAI Cloud — Nova (Female Warm)</option>
                      <option value="openai_shimmer">⚡ OpenAI Cloud — Shimmer (Female Expressive)</option>
                    </optgroup>
                    <optgroup label="🇮🇳 Regional Indian Languages (Cartesia Cloud)">
                      <option value="cartesia_ta_female">🇮🇳 Cartesia — Tamil Female (ta-IN)</option>
                      <option value="cartesia_te_female">🇮🇳 Cartesia — Telugu Female (te-IN)</option>
                      <option value="cartesia_bn_female">🇮🇳 Cartesia — Bengali Female (bn-IN)</option>
                      <option value="cartesia_mr_female">🇮🇳 Cartesia — Marathi Female (mr-IN)</option>
                      <option value="cartesia_gu_female">🇮🇳 Cartesia — Gujarati Female (gu-IN)</option>
                      <option value="cartesia_kn_female">🇮🇳 Cartesia — Kannada Female (kn-IN)</option>
                      <option value="cartesia_ml_female">🇮🇳 Cartesia — Malayalam Female (ml-IN)</option>
                      <option value="cartesia_pa_female">🇮🇳 Cartesia — Punjabi Female (pa-IN)</option>
                      <option value="cartesia_ur_female">🇮🇳 Cartesia — Urdu Female (ur-IN)</option>
                    </optgroup>
                    <optgroup label="🧠 Kokoro-82M Neural On-Premise (Fast Local)">
                      <option value="af_sarah">🧠 Kokoro Neural — Sarah (Female 24kHz)</option>
                      <option value="am_adam">🧠 Kokoro Neural — Adam (Male 24kHz)</option>
                    </optgroup>
                    <optgroup label="🏠 Local On-Premise Offline Voices">
                      <option value="hi_pratham">🏠 Local On-Premise — Hindi Pratham (Male Outreach)</option>
                      <option value="hi_aditi">🏠 Local On-Premise — Hindi Aditi (Female Clear)</option>
                      <option value="en_sarah">🏠 Local On-Premise — English Sarah (Female)</option>
                      <option value="en_bella">🏠 Local On-Premise — English Bella (Female Expressive)</option>
                      <option value="en_michael">🏠 Local On-Premise — English Michael (Male)</option>
                    </optgroup>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Spoken Script / Prompt Text</label>
                <textarea
                  rows={4}
                  required
                  placeholder="Type your campaign script text here..."
                  value={scriptContent}
                  onChange={(e) => setScriptContent(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-slate-200 focus:outline-none focus:border-brand-500 text-sm"
                ></textarea>
              </div>

              {/* AUDIENCE & CONTACT SELECTION SECTION */}
              <div className="space-y-2 pt-2 border-t border-slate-800">
                <div className="flex items-center justify-between">
                  <label className="text-slate-200 font-semibold text-xs flex items-center space-x-1.5">
                    <Users className="w-4 h-4 text-brand-400" />
                    <span>Select Contacts to Call</span>
                  </label>
                  <div className="flex bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-[11px]">
                    <button
                      type="button"
                      onClick={() => setContactMode('crm')}
                      className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                        contactMode === 'crm' ? 'bg-brand-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      CRM Leads ({contacts.length})
                    </button>
                    <button
                      type="button"
                      onClick={() => setContactMode('manual')}
                      className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                        contactMode === 'manual' ? 'bg-brand-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Paste Numbers
                    </button>
                  </div>
                </div>

                {/* CRM Contacts Picker Tab */}
                {contactMode === 'crm' && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="relative flex-1">
                        <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                        <input
                          type="text"
                          placeholder="Search leads by name or phone..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-slate-200 text-xs focus:outline-none focus:border-brand-500"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={handleToggleSelectAll}
                        className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium border border-slate-700 shrink-0"
                      >
                        {filteredContacts.length > 0 && filteredContacts.every(c => selectedContactIds.includes(c.id))
                          ? 'Deselect All'
                          : `Select All (${filteredContacts.length})`}
                      </button>
                    </div>

                    <div className="text-[11px] text-slate-400 flex justify-between px-1">
                      <span>Selected: <strong className="text-brand-400">{selectedContactIds.length}</strong> contacts</span>
                      <span>Total CRM Leads: {contacts.length}</span>
                    </div>

                    <div className="max-h-44 overflow-y-auto space-y-1 bg-slate-950/60 border border-slate-800/80 rounded-xl p-2 divide-y divide-slate-900/60">
                      {filteredContacts.length === 0 ? (
                        <div className="text-center py-4 text-xs text-slate-500">
                          {contacts.length === 0 ? 'No contacts available in CRM yet.' : 'No matching contacts found.'}
                        </div>
                      ) : (
                        filteredContacts.map(contact => {
                          const isSelected = selectedContactIds.includes(contact.id);
                          return (
                            <label
                              key={contact.id}
                              className={`flex items-center justify-between p-1.5 rounded-lg cursor-pointer transition-colors ${
                                isSelected ? 'bg-brand-500/10 text-slate-100' : 'hover:bg-slate-900/60 text-slate-300'
                              }`}
                            >
                              <div className="flex items-center space-x-2.5 truncate">
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => handleToggleContact(contact.id)}
                                  className="accent-brand-500 rounded cursor-pointer"
                                />
                                <div className="truncate">
                                  <div className="font-medium text-xs text-slate-200 truncate">{contact.name || 'Unnamed Lead'}</div>
                                  <div className="text-[11px] font-mono text-slate-400">{contact.phone_number}</div>
                                </div>
                              </div>
                              <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono shrink-0 ml-2">
                                {contact.status || 'ACTIVE'}
                              </span>
                            </label>
                          );
                        })
                      )}
                    </div>
                  </div>
                )}

                {/* Manual Phone Numbers Tab */}
                {contactMode === 'manual' && (
                  <div className="space-y-1.5">
                    <textarea
                      rows={3}
                      placeholder="Paste phone numbers separated by commas or new lines, e.g.:&#10;+918830718466&#10;09876543210&#10;08047283364"
                      value={manualNumbers}
                      onChange={(e) => setManualNumbers(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl p-2.5 text-slate-200 text-xs font-mono focus:outline-none focus:border-brand-500"
                    />
                    <p className="text-[11px] text-slate-500">
                      Numbers entered here will be registered into the CRM database and linked to this campaign.
                    </p>
                  </div>
                )}

                {/* MicroSIP Softphone Option */}
                <label className="flex items-center space-x-2 pt-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeSoftphone}
                    onChange={(e) => setIncludeSoftphone(e.target.checked)}
                    className="accent-brand-500 rounded cursor-pointer"
                  />
                  <span className="text-xs text-slate-300">
                    Include local <strong>MicroSIP Softphone (<code className="text-brand-400 font-mono">test1000</code>)</strong> for instant testing
                  </span>
                </label>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Max Queue Concurrency ({concurrency} parallel slots)</label>
                <input
                  type="range"
                  min={1}
                  max={20}
                  value={concurrency}
                  onChange={(e) => setConcurrency(parseInt(e.target.value))}
                  className="w-full accent-brand-500"
                />
              </div>

              <div className="flex justify-end space-x-3 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 font-medium text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium text-xs shadow-lg shadow-brand-600/20"
                >
                  Create & Assign Contacts
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Script Modal */}
      {editingCampaign && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="glass-panel w-full max-w-lg p-6 rounded-2xl border border-slate-800 space-y-4">
            <h3 className="text-lg font-bold text-slate-100">✏️ Edit Campaign Script</h3>
            <div>
              <label className="block text-slate-300 font-medium mb-1 text-xs">Neural Voice Model</label>
              <select
                value={editVoice}
                onChange={(e) => setEditVoice(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-xl p-2.5 text-slate-200 text-xs focus:outline-none focus:border-brand-500"
              >
                <option value="deepgram_aura_asteria">Deepgram Aura Asteria (Cloud Neural)</option>
                <option value="cartesia_hi_sonic">Cartesia Hindi Sonic (Cloud Neural)</option>
                <option value="hi_female">Kokoro Female Sarah (Local ONNX)</option>
                <option value="hi_pratham">Piper Hindi Pratham (Local)</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1 text-xs">Spoken Campaign Script</label>
              <textarea
                rows={5}
                value={editScript}
                onChange={(e) => setEditScript(e.target.value)}
                placeholder="Type your new custom campaign script text here..."
                className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-slate-200 text-xs focus:outline-none focus:border-brand-500"
              />
            </div>
            <div className="flex justify-end space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setEditingCampaign(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                className="px-5 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold shadow-lg shadow-brand-600/20"
              >
                Save Updated Script
              </button>
            </div>
          </div>
        </div>
      )}

      {/* View Campaign Contacts Modal */}
      {viewContactsCampaign && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="glass-panel w-full max-w-xl p-5 md:p-6 rounded-2xl border border-slate-800 space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div>
                <h3 className="text-base font-bold text-slate-100 flex items-center space-x-2">
                  <Users className="w-4 h-4 text-brand-400" />
                  <span>Campaign Contacts: {viewContactsCampaign.name}</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  {campaignContacts.length} total contact{campaignContacts.length !== 1 ? 's' : ''} assigned to this campaign
                </p>
              </div>
              <button
                onClick={() => setViewContactsCampaign(null)}
                className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {loadingContacts ? (
                <div className="text-center py-8 text-xs text-slate-400 flex items-center justify-center space-x-2">
                  <RefreshCw className="w-4 h-4 animate-spin text-brand-400" />
                  <span>Loading campaign contacts...</span>
                </div>
              ) : campaignContacts.length === 0 ? (
                <div className="text-center py-8 text-xs text-slate-500">
                  No contacts found in this campaign.
                </div>
              ) : (
                campaignContacts.map(cc => (
                  <div
                    key={cc.id}
                    className="p-3 bg-slate-900/70 border border-slate-800 rounded-xl flex items-center justify-between gap-3"
                  >
                    <div className="truncate">
                      <div className="text-xs font-semibold text-slate-200 truncate">{cc.name}</div>
                      <div className="text-xs font-mono text-slate-400 flex items-center space-x-1 mt-0.5">
                        <Phone className="w-3 h-3 text-slate-500" />
                        <span>{cc.phone_number}</span>
                      </div>
                      {cc.last_attempt_at && (
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Last dial: {new Date(cc.last_attempt_at).toLocaleTimeString()}
                        </div>
                      )}
                    </div>
                    <div className="text-right space-y-1 shrink-0">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                        cc.status === 'COMPLETED' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        cc.status === 'CALLING' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                        cc.status === 'FAILED' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                        cc.status === 'RETRY' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        'bg-slate-800 text-slate-400'
                      }`}>
                        {cc.status}
                      </span>
                      <div className="text-[10px] text-slate-400">
                        {cc.attempt_count} attempt{cc.attempt_count !== 1 ? 's' : ''}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setViewContactsCampaign(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Single Campaign Delete Confirmation Modal */}
      {campaignToDelete && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="glass-panel w-full max-w-md p-6 rounded-2xl border border-slate-800 space-y-4 shadow-2xl">
            <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 mx-auto">
              <AlertTriangle className="w-6 h-6" />
            </div>

            <div className="text-center space-y-1.5">
              <h3 className="text-base font-bold text-slate-100">Delete Campaign</h3>
              <p className="text-xs text-slate-400">
                Are you sure you want to delete <strong className="text-slate-200">"{campaignToDelete.name}"</strong>?
              </p>
            </div>

            <div className="p-3 rounded-xl bg-rose-500/5 border border-rose-500/20 text-[11px] text-rose-300 space-y-1">
              <div className="font-semibold flex items-center space-x-1">
                <Trash2 className="w-3.5 h-3.5" />
                <span>Permanent Deletion Warning</span>
              </div>
              <p className="text-rose-300/80">
                This will immediately stop active calling tasks and remove all queued contacts, call attempts, and progress records for this campaign.
              </p>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-2 border-t border-slate-800/80">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setCampaignToDelete(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleConfirmDeleteSingle}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-lg shadow-rose-600/30 flex items-center space-x-1.5 transition-all disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Yes, Delete Campaign</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Delete Confirmation Modal */}
      {showBulkDeleteModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="glass-panel w-full max-w-lg p-6 rounded-2xl border border-slate-800 space-y-4 shadow-2xl">
            <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 mx-auto">
              <Trash2 className="w-6 h-6" />
            </div>

            <div className="text-center space-y-1.5">
              <h3 className="text-base font-bold text-slate-100">
                Delete {selectedCampaignIds.length} Selected Campaign{selectedCampaignIds.length !== 1 ? 's' : ''}
              </h3>
              <p className="text-xs text-slate-400">
                Are you sure you want to permanently delete these <strong className="text-slate-200">{selectedCampaignIds.length}</strong> campaigns?
              </p>
            </div>

            <div className="max-h-40 overflow-y-auto space-y-1.5 p-2 bg-slate-900/60 rounded-xl border border-slate-800">
              {campaigns
                .filter(c => selectedCampaignIds.includes(c.id))
                .map(c => (
                  <div key={c.id} className="flex items-center justify-between p-2 rounded-lg bg-slate-800/50 text-xs">
                    <span className="font-medium text-slate-200 truncate">{c.name}</span>
                    <span className="text-[10px] font-mono text-slate-400 shrink-0 ml-2">{c.status}</span>
                  </div>
                ))}
            </div>

            <div className="p-3 rounded-xl bg-rose-500/5 border border-rose-500/20 text-[11px] text-rose-300">
              All assigned contact queues and attempt logs for the selected campaigns will be wiped immediately.
            </div>

            <div className="flex items-center justify-end space-x-3 pt-2 border-t border-slate-800/80">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setShowBulkDeleteModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleConfirmBulkDelete}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-lg shadow-rose-600/30 flex items-center space-x-1.5 transition-all disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Delete {selectedCampaignIds.length} Campaigns</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
