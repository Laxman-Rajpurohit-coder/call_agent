import React, { useEffect } from 'react';

interface SEOHeadProps {
  activeTab: string;
}

const TAB_SEO_MAP: Record<string, { title: string; description: string; canonical: string }> = {
  'overview': {
    title: 'Operations Overview | Superfone AI Voice Hub',
    description: 'Real-time overview of active SIP calls, microservices cluster health, human handoffs, and voice QA metrics.',
    canonical: 'https://superfone.ai/#overview'
  },
  'org-dashboard': {
    title: 'Organization Dashboard | Superfone AI Voice Hub',
    description: 'High‑level system health, campaign stats, and team productivity overview.',
    canonical: 'https://superfone.ai/#org-dashboard'
  },
  'team': {
    title: 'Team Activity & Agent Progress | Superfone AI Voice Ops',
    description: 'Track sales agent call volume, daily call target progress, talk time, active status, and individual agent performance analytics.',
    canonical: 'https://superfone.ai/#team'
  },
  'agent-panel': {
    title: 'Agent Softphone Panel | Superfone Telephony',
    description: 'Sales Agent desktop panel with softphone dialer, SIP extension status, active call management, and lead details.',
    canonical: 'https://superfone.ai/#agent-panel'
  },
  'agent-login': {
    title: 'Sales Agent Login & Portal | Superfone AI Telephony',
    description: 'Secure PIN login portal for sales agents and telephony staff.',
    canonical: 'https://superfone.ai/#agent-login'
  },
  'live-monitor': {
    title: 'Live Telephony Monitor & Audio Stream | Superfone AI',
    description: 'Real-time live call monitoring, acoustic audio waveform visualization, and STT transcript streaming.',
    canonical: 'https://superfone.ai/#live-monitor'
  },
  'crm': {
    title: 'Voice CRM & Contacts | Superfone AI Voice Hub',
    description: 'Manage sales leads, phone contacts, lead owner assignments, call session logs, and WhatsApp interactions.',
    canonical: 'https://superfone.ai/#crm'
  },
  'tasks': {
    title: 'To-Do & Follow-up Tasks | Superfone AI',
    description: 'Automated round-robin lead task distribution, callback reminders, and follow-up tracking.',
    canonical: 'https://superfone.ai/#tasks'
  },
  'campaigns': {
    title: 'Voice Campaign Engine | Superfone AI Platform',
    description: 'Launch automated AI voice campaigns, concurrency sweeps, and dialer scripts.',
    canonical: 'https://superfone.ai/#campaigns'
  },
  'voice-studio': {
    title: 'AI Voice Studio & Prompt Engineering | Superfone AI',
    description: 'Configure Hindi phonetic TTS normalization, Cartesia/Deepgram voice models, and conversational system prompts.',
    canonical: 'https://superfone.ai/#voice-studio'
  },
  'evaluations': {
    title: 'Evaluation & QA Benchmarks | Superfone AI',
    description: 'Sub-second latency benchmarks, Word Error Rate (WER) evaluations, and audio quality QA reports.',
    canonical: 'https://superfone.ai/#evaluations'
  },
  'load-testing': {
    title: 'Load & Concurrency Capacity Testing | Superfone AI',
    description: 'SIP concurrency sweeps, latency P50/P95 benchmarks, and stress testing analytics.',
    canonical: 'https://superfone.ai/#load-testing'
  },
  'settings': {
    title: 'System Settings & SIP Configuration | Superfone AI',
    description: 'Configure Asterisk SIP trunking, Vobiz webhook URLs, microservice endpoints, and API credentials.',
    canonical: 'https://superfone.ai/#settings'
  }
};

export const SEOHead: React.FC<SEOHeadProps> = ({ activeTab }) => {
  useEffect(() => {
    const seoData = TAB_SEO_MAP[activeTab] || {
      title: 'Superfone AI Voice Operations Platform',
      description: 'Ultra low-latency real-time AI telephony, speech analytics, CRM integration, and voice campaign control.',
      canonical: 'https://superfone.ai/'
    };

    // Update document title
    document.title = seoData.title;

    // Update meta description
    let metaDescription = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!metaDescription) {
      metaDescription = document.createElement('meta');
      metaDescription.name = 'description';
      document.head.appendChild(metaDescription);
    }
    metaDescription.content = seoData.description;

    // Update Open Graph title & description
    let ogTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"]');
    if (ogTitle) ogTitle.content = seoData.title;

    let ogDesc = document.querySelector<HTMLMetaElement>('meta[property="og:description"]');
    if (ogDesc) ogDesc.content = seoData.description;

    let ogUrl = document.querySelector<HTMLMetaElement>('meta[property="og:url"]');
    if (ogUrl) ogUrl.content = seoData.canonical;

    // Update canonical URL tag
    let canonicalLink = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonicalLink) {
      canonicalLink = document.createElement('link');
      canonicalLink.rel = 'canonical';
      document.head.appendChild(canonicalLink);
    }
    canonicalLink.href = seoData.canonical;

  }, [activeTab]);

  return null;
};
