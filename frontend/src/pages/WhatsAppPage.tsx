import React, { useState, useEffect } from 'react';
import { MessageSquare, Send, Phone, User, Search, Check, CheckCheck, Clock } from 'lucide-react';
import { WhatsAppChat } from '../types';

export const WhatsAppPage: React.FC = () => {
  const [chats, setChats] = useState<WhatsAppChat[]>([]);
  const [selectedChat, setSelectedChat] = useState<WhatsAppChat | null>(null);
  const [newMsg, setNewMsg] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const fetchChats = async () => {
    try {
      const res = await fetch('/api/v1/whatsapp/chats');
      if (res.ok) {
        const data = await res.json();
        setChats(data);
        if (data.length > 0 && !selectedChat) {
          setSelectedChat(data[0]);
        }
      }
    } catch (ex) {
      console.error('Failed to fetch whatsapp chats', ex);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChats();
    const interval = setInterval(fetchChats, 3000);
    return () => clearInterval(interval);
  }, []);

  const sendMessage = async () => {
    if (!newMsg.trim() || !selectedChat) return;
    try {
      await fetch('/api/v1/whatsapp/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_id: selectedChat.contact_id,
          phone_number: selectedChat.phone_number,
          message_text: newMsg
        })
      });
      setNewMsg('');
      fetchChats();
    } catch (ex) {
      console.error('Failed to send whatsapp message', ex);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight flex items-center gap-2">
            <MessageSquare className="w-6 h-6 text-emerald-600 dark:text-emerald-400" /> WhatsApp Business
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">Direct WhatsApp chats, auto-follow ups, and lead messaging</p>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6 h-[550px]">
        {/* Chat List */}
        <div className="col-span-4 bg-white dark:bg-slate-900/70 rounded-xl border border-slate-200 dark:border-slate-800/80 flex flex-col overflow-hidden shadow-sm">
          <div className="p-3.5 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search chats..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 bg-slate-100 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-750 rounded-lg text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-slate-200 dark:divide-slate-800/60">
            {chats.map(chat => (
              <div
                key={chat.phone_number}
                onClick={() => setSelectedChat(chat)}
                className={`p-3.5 cursor-pointer transition-colors flex items-center gap-3 ${selectedChat?.phone_number === chat.phone_number ? 'bg-emerald-50 dark:bg-emerald-500/15 border-l-4 border-emerald-500' : 'hover:bg-slate-50 dark:hover:bg-slate-800/30'}`}
              >
                <div className="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 flex items-center justify-center font-bold text-sm shrink-0">
                  {chat.contact_name.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white truncate">{chat.contact_name}</h4>
                    <span className="text-[10px] text-slate-500 shrink-0">
                      {chat.messages.length > 0 ? new Date(chat.messages[chat.messages.length - 1].timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-400 truncate mt-0.5">
                    {chat.messages.length > 0 ? chat.messages[chat.messages.length - 1].message_text : 'No messages'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Chat Window */}
        <div className="col-span-8 bg-white dark:bg-slate-900/70 rounded-xl border border-slate-200 dark:border-slate-800/80 flex flex-col overflow-hidden shadow-sm">
          {selectedChat ? (
            <>
              <div className="p-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 flex items-center justify-center font-bold text-sm">
                    {selectedChat.contact_name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-900 dark:text-white text-sm">{selectedChat.contact_name}</h3>
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1 mt-0.5">
                      <Phone className="w-3 h-3" /> {selectedChat.phone_number}
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex-1 p-5 overflow-y-auto space-y-4 bg-slate-50 dark:bg-slate-950/40">
                {selectedChat.messages.map(msg => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`p-3 rounded-2xl max-w-md text-sm ${
                        msg.direction === 'outbound'
                          ? 'bg-emerald-600 text-white rounded-tr-none shadow-md'
                          : 'bg-white dark:bg-slate-800/80 text-slate-900 dark:text-slate-200 rounded-tl-none border border-slate-200 dark:border-slate-750 shadow-sm'
                      }`}
                    >
                      <p>{msg.message_text}</p>
                      <div className="text-[10px] text-slate-300 text-right mt-1 flex items-center justify-end gap-1 opacity-90">
                        {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        <CheckCheck className="w-3 h-3 text-emerald-200" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="Type a WhatsApp message..."
                    value={newMsg}
                    onChange={e => setNewMsg(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && sendMessage()}
                    className="flex-1 px-4 py-2.5 bg-white dark:bg-slate-950/80 border border-slate-300 dark:border-slate-750 rounded-xl text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none"
                  />
                  <button
                    onClick={sendMessage}
                    className="p-2.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 rounded-xl font-bold transition-colors flex items-center justify-center shrink-0"
                  >
                    <Send className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">Select a chat to start messaging</div>
          )}
        </div>
      </div>
    </div>
  );
};
