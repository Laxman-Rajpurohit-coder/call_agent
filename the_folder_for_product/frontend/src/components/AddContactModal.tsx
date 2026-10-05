import React, { useState, useEffect } from 'react';
import { X, UserPlus, Phone, Mail, Building, Tag, AlertTriangle, CheckCircle, ArrowRight, Loader2 } from 'lucide-react';
import { Contact } from '../types';

interface AddContactModalProps {
  isOpen: boolean;
  onClose: () => void;
  onContactCreated: (contact: Contact) => void;
  onOpenExisting: (contactId: string) => void;
}

export const AddContactModal: React.FC<AddContactModalProps> = ({
  isOpen,
  onClose,
  onContactCreated,
  onOpenExisting
}) => {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [status, setStatus] = useState('lead');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [customTagInput, setCustomTagInput] = useState('');

  const [checkingDuplicate, setCheckingDuplicate] = useState(false);
  const [duplicateInfo, setDuplicateInfo] = useState<any | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Check duplicate when phone or email changes
  useEffect(() => {
    const cleanPhone = phone.replace(/[^0-9+]/g, '');
    if (cleanPhone.length >= 10 || (email && email.includes('@'))) {
      const timer = setTimeout(async () => {
        setCheckingDuplicate(true);
        try {
          const res = await fetch('/api/v1/contacts/check-duplicate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone: cleanPhone, email: email.trim() || undefined })
          });
          const text = await res.text();
          const data = text ? JSON.parse(text) : {};
          if (data && data.duplicate) {
            setDuplicateInfo(data.duplicate);
          } else {
            setDuplicateInfo(null);
          }
        } catch (e) {
          console.warn('Duplicate check error:', e);
        } finally {
          setCheckingDuplicate(false);
        }
      }, 400);

      return () => clearTimeout(timer);
    } else {
      setDuplicateInfo(null);
    }
  }, [phone, email]);

  if (!isOpen) return null;

  const handleToggleTag = (tag: string) => {
    setSelectedTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    );
  };

  const handleAddCustomTag = () => {
    if (!customTagInput.trim()) return;
    const tag = customTagInput.trim().toUpperCase();
    if (!selectedTags.includes(tag)) {
      setSelectedTags([...selectedTags, tag]);
    }
    setCustomTagInput('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phone.trim()) {
      setError('Phone number is required');
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const res = await fetch('/api/v1/contacts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone_number: phone.trim(),
          name: name.trim() || undefined,
          email: email.trim() || undefined,
          company: company.trim() || undefined,
          status,
          tags: selectedTags,
          preferred_language: 'hi'
        })
      });
      const text = await res.text();
      let newContact: any = null;
      try {
        newContact = text ? JSON.parse(text) : null;
      } catch {}

      if (!res.ok) {
        throw new Error((newContact && newContact.detail) || text || 'Failed to save contact');
      }
      if (newContact) onContactCreated(newContact);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Error creating contact');
    } finally {
      setSaving(false);
    }
  };

  const PRESET_TAGS = ['VIP', 'HOT LEAD', 'FOLLOW-UP', 'INTERESTED', 'CUSTOMER'];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-150">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden text-slate-100 space-y-4 p-6">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-brand-500/10 text-brand-400 border border-brand-500/20">
              <UserPlus className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-white">Add New Contact</h3>
              <p className="text-xs text-slate-400">Single customer identity record across all channels</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Duplicate Warning Banner */}
        {duplicateInfo && (
          <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs space-y-2">
            <div className="flex items-center justify-between font-semibold">
              <span className="flex items-center space-x-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <span>Existing Contact Detected</span>
              </span>
              <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-amber-500/20">
                Matches {duplicateInfo.match_field}
              </span>
            </div>
            <p className="text-slate-300 text-[11px] leading-relaxed">
              <strong>{duplicateInfo.name}</strong> ({duplicateInfo.phone_number}) is already in your database.
            </p>
            <button
              type="button"
              onClick={() => {
                onClose();
                onOpenExisting(duplicateInfo.contact_id);
              }}
              className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center space-x-1 shadow-sm transition-all"
            >
              <span>Open Existing Contact 360</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Full Name</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Rahul Sharma"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-brand-500"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1 font-medium">
                Phone Number <span className="text-rose-400">*</span>
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  placeholder="9876543210"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-brand-500"
                />
                {checkingDuplicate && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400 absolute right-3 top-2.5" />
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="rahul@example.com"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-brand-500"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Company / Clinic</label>
              <input
                type="text"
                value={company}
                onChange={e => setCompany(e.target.value)}
                placeholder="Acme Corp"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-brand-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Lifecycle Status</label>
              <select
                value={status}
                onChange={e => setStatus(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-brand-500"
              >
                <option value="lead">Lead</option>
                <option value="interested">Interested</option>
                <option value="customer">Customer</option>
                <option value="follow-up">Follow-up</option>
                <option value="not-interested">Not Interested</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Add Tag</label>
              <div className="flex space-x-1">
                <input
                  type="text"
                  value={customTagInput}
                  onChange={e => setCustomTagInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddCustomTag();
                    }
                  }}
                  placeholder="Custom tag..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-2.5 py-2 text-slate-100 text-xs focus:outline-none focus:border-brand-500"
                />
                <button
                  type="button"
                  onClick={handleAddCustomTag}
                  className="px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold"
                >
                  Add
                </button>
              </div>
            </div>
          </div>

          {/* Preset Tag Badges */}
          <div className="space-y-1.5">
            <div className="text-[11px] text-slate-400">Quick Tags:</div>
            <div className="flex flex-wrap gap-1.5">
              {PRESET_TAGS.map(tag => {
                const isSelected = selectedTags.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => handleToggleTag(tag)}
                    className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold transition-all ${
                      isSelected
                        ? 'bg-brand-600 text-white'
                        : 'bg-slate-800/80 text-slate-400 hover:text-slate-200 border border-slate-750'
                    }`}
                  >
                    {tag}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Form Actions */}
          <div className="flex items-center justify-end space-x-2 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-xs font-semibold"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-semibold shadow-lg shadow-brand-600/20 flex items-center space-x-1.5 transition-all"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UserPlus className="w-3.5 h-3.5" />}
              <span>Save Contact</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
