import React, { useState, useEffect } from 'react';
import { Phone, PhoneOff, AlertTriangle, User, MessageSquare, Clock } from 'lucide-react';

export interface HandoffOffer {
  call_id: string;
  customer_name: string;
  customer_phone: string;
  lead_id?: string;
  reason: 'CUSTOMER_REQUESTED_HUMAN' | 'AI_OUT_OF_SCOPE' | 'AI_LOW_CONFIDENCE' | 'CUSTOMER_ESCALATION' | string;
  ai_summary: string;
  expires_at?: string;
}

interface IncomingCallCardProps {
  offer: HandoffOffer | null;
  agentId: string;
  onAccept: (callId: string) => Promise<void>;
  onReject: (callId: string) => Promise<void>;
  onClose: () => void;
  statusMessage?: string | null;
}

export const IncomingCallCard: React.FC<IncomingCallCardProps> = ({
  offer,
  agentId,
  onAccept,
  onReject,
  onClose,
  statusMessage
}) => {
  const [timeLeft, setTimeLeft] = useState<number>(15);
  const [isAnswering, setIsAnswering] = useState<boolean>(false);

  useEffect(() => {
    if (!offer) return;
    setTimeLeft(15);
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          onReject(offer.call_id);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [offer]);

  if (!offer && !statusMessage) return null;

  const getReasonBadge = (reason: string) => {
    switch (reason) {
      case 'CUSTOMER_REQUESTED_HUMAN':
        return <span className="bg-indigo-500/20 text-indigo-300 text-xs px-2.5 py-1 rounded-full border border-indigo-500/30 flex items-center gap-1"><User className="w-3 h-3" /> Customer Requested Human</span>;
      case 'AI_OUT_OF_SCOPE':
        return <span className="bg-amber-500/20 text-amber-300 text-xs px-2.5 py-1 rounded-full border border-amber-500/30 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> AI Out of Scope</span>;
      case 'AI_LOW_CONFIDENCE':
        return <span className="bg-orange-500/20 text-orange-300 text-xs px-2.5 py-1 rounded-full border border-orange-500/30 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Low Confidence Intent</span>;
      case 'CUSTOMER_ESCALATION':
        return <span className="bg-red-500/20 text-red-300 text-xs px-2.5 py-1 rounded-full border border-red-500/30 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Escalation Warning</span>;
      default:
        return <span className="bg-slate-500/20 text-slate-300 text-xs px-2.5 py-1 rounded-full border border-slate-500/30">Handoff Request</span>;
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 w-96 bg-slate-900/95 backdrop-blur-xl border-2 border-indigo-500/40 rounded-2xl shadow-2xl p-5 text-white animate-bounce-short">
      {statusMessage ? (
        <div className="text-center py-4 space-y-2">
          <div className="w-12 h-12 bg-indigo-500/20 rounded-full flex items-center justify-center mx-auto text-indigo-400">
            <Clock className="w-6 h-6 animate-spin" />
          </div>
          <p className="text-sm font-medium text-slate-200">{statusMessage}</p>
        </div>
      ) : offer ? (
        <div className="space-y-4">
          {/* Header & Ringing Timer */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </span>
              <h3 className="font-semibold text-emerald-400 text-sm tracking-wide">INCOMING CUSTOMER CALL</h3>
            </div>
            <div className="flex items-center gap-1 text-xs font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded-md border border-slate-700">
              <Clock className="w-3 h-3 text-emerald-400" />
              <span>{timeLeft}s</span>
            </div>
          </div>

          {/* Customer Details */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-start">
              <div>
                <h4 className="text-lg font-bold text-slate-100">{offer.customer_name || 'Rahul Sharma'}</h4>
                <p className="text-xs font-mono text-slate-400">{offer.customer_phone}</p>
              </div>
              {offer.lead_id && (
                <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
                  #{offer.lead_id}
                </span>
              )}
            </div>
            <div className="pt-1">{getReasonBadge(offer.reason)}</div>
          </div>

          {/* AI Summary Box */}
          <div className="bg-slate-950/80 rounded-xl p-3 border border-slate-800/80 space-y-1 text-xs">
            <div className="flex items-center gap-1 text-slate-400 font-medium">
              <MessageSquare className="w-3.5 h-3.5 text-indigo-400" />
              <span>AI Conversation Summary:</span>
            </div>
            <p className="text-slate-300 leading-relaxed italic pl-4 border-l-2 border-indigo-500/50">
              "{offer.ai_summary || 'Customer was speaking with AI receptionist Riya.'}"
            </p>
          </div>

          {/* Action Buttons */}
          <div className="grid grid-cols-2 gap-3 pt-1">
            <button
              onClick={async () => {
                setIsAnswering(true);
                await onAccept(offer.call_id);
                setIsAnswering(false);
              }}
              disabled={isAnswering}
              className="w-full bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white font-semibold py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-emerald-900/30 transition-all cursor-pointer disabled:opacity-50"
            >
              <Phone className="w-4 h-4 fill-white" />
              <span>{isAnswering ? 'Connecting...' : 'ANSWER'}</span>
            </button>
            <button
              onClick={() => onReject(offer.call_id)}
              disabled={isAnswering}
              className="w-full bg-rose-600/20 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500/30 font-semibold py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 transition-all cursor-pointer disabled:opacity-50"
            >
              <PhoneOff className="w-4 h-4" />
              <span>REJECT</span>
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
};
