const express = require('express');
const router = express.Router();
const prisma = require('../db');

// POST/GET /api/telephony/webhook - Unified Webhook receiver for CPaaS (Exotel Stream / Twilio / SIP)
const handleWebhook = async (req, res) => {
  try {
    const { From, To, CallSid, CallStatus } = { ...req.query, ...req.body };
    console.log(`[Telephony Webhook] 📥 Call Event: Method=${req.method}, From=${From}, To=${To}, Status=${CallStatus || 'active'}`);
    console.log(`[Telephony Webhook] Headers: User-Agent=${req.headers['user-agent']}, Accept=${req.headers['accept']}`);
    console.log(`[Telephony Webhook] Query:`, JSON.stringify(req.query));
    console.log(`[Telephony Webhook] Body:`, JSON.stringify(req.body));

    const host = req.headers.host || process.env.RAILWAY_PUBLIC_DOMAIN || 'callagent-production-5b4e.up.railway.app';
    const isSecure = req.secure || host.includes('railway.app') || host.includes('ngrok') || req.headers['x-forwarded-proto'] === 'https';
    const wsScheme = isSecure ? 'wss' : 'ws';
    const streamUrl = `${wsScheme}://${host}/media-stream`;

    // Exotel Stream Applet returns JSON wss URL if requested or format=json or Exotel Passthru
    if (req.headers.accept?.includes('application/json') || req.query.format === 'json') {
      console.log(`[Telephony Webhook] ⏩ Returning JSON Stream URL: ${streamUrl}`);
      return res.json({ url: streamUrl, select: 'stream', status: 'success' });
    }

    console.log(`[Telephony Webhook] ⏩ Returning XML Stream Response: ${streamUrl}`);
    return res.type('text/xml').send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="${streamUrl}" />
    </Connect>
</Response>`);
  } catch (error) {
    console.error('Error handling telephony webhook:', error);
    res.status(500).type('text/xml').send(`<?xml version="1.0" encoding="UTF-8"?><Response><Say>An error occurred connecting your call.</Say></Response>`);
  }
};

router.get('/webhook', handleWebhook);
router.post('/webhook', handleWebhook);

// POST /api/telephony/outbound-call - Trigger automated outbound AI call via Vobiz or Exotel API
router.post('/outbound-call', async (req, res) => {
  try {
    const to = req.body?.to || req.query?.to;
    if (!to) {
      return res.status(400).json({ success: false, error: 'Recipient phone number (to) is required.' });
    }

    const provider = req.body?.provider || 'vobiz';
    const vobizAuthId = process.env.VOBIZ_AUTH_ID;
    const vobizToken = process.env.VOBIZ_AUTH_TOKEN;
    const vobizCallerId = process.env.VOBIZ_CALLER_ID || '918064269009';
    const railwayDomain = process.env.RAILWAY_PUBLIC_DOMAIN || 'callagent-production-5b4e.up.railway.app';
    const vobizPublicUrl = (process.env.VOBIZ_PUBLIC_URL && !process.env.VOBIZ_PUBLIC_URL.includes('ngrok'))
      ? process.env.VOBIZ_PUBLIC_URL.replace(/\/$/, '')
      : `https://${railwayDomain}`;

    const digitsOnly = to.replace(/\D/g, '');
    let cleanVobizTo = digitsOnly;
    if (digitsOnly.length === 10) {
      cleanVobizTo = '91' + digitsOnly;
    }

    // 1. Primary: VOBIZ API
    if (vobizAuthId && vobizToken && (provider === 'vobiz' || !process.env.EXOTEL_API_KEY)) {
      const vobizUrl = `https://api.vobiz.ai/api/v1/Account/${vobizAuthId}/Call/`;
      const answerUrl = `${vobizPublicUrl}/answer`;

      const vobizRes = await fetch(vobizUrl, {
        method: 'POST',
        headers: {
          'X-Auth-ID': vobizAuthId,
          'X-Auth-Token': vobizToken,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          from: vobizCallerId,
          to: cleanVobizTo,
          answer_url: answerUrl,
          answer_method: 'POST'
        })
      });

      const data = await vobizRes.json();
      console.log(`[Vobiz Outbound Call] Dialed ${cleanVobizTo} via Vobiz API: HTTP ${vobizRes.status}`, data);
      if (!vobizRes.ok) {
        return res.status(vobizRes.status).json({ success: false, error: data.message || 'Vobiz API error' });
      }
      return res.json({ success: true, provider: 'vobiz', data });
    }

    // 2. Secondary Fallback: Exotel API
    const accountSid = process.env.EXOTEL_ACCOUNT_SID || 'snazzyitsolutions1';
    const apiKey = process.env.EXOTEL_API_KEY;
    const apiToken = process.env.EXOTEL_API_TOKEN;
    const callerId = process.env.EXOTEL_VIRTUAL_NUMBER || '08047283364';

    if (!apiKey || !apiToken) {
      return res.status(500).json({ success: false, error: 'Neither Vobiz nor Exotel credentials configured in .env' });
    }

    const cleanTo = to.replace(/\s+/g, '').replace(/^\+91/, '0');
    const authHeader = 'Basic ' + Buffer.from(`${apiKey}:${apiToken}`).toString('base64');
    const exotelUrl = `https://api.exotel.com/v1/Accounts/${accountSid}/Calls/connect.json`;

    // Route call through public Railway webhook to start Voicebot media stream
    const publicDomain = (process.env.PUBLIC_DOMAIN && !process.env.PUBLIC_DOMAIN.includes('ngrok'))
      ? process.env.PUBLIC_DOMAIN
      : (process.env.RAILWAY_PUBLIC_DOMAIN || 'callagent-production-5b4e.up.railway.app');
    const webhookUrl = `https://${publicDomain}/api/telephony/webhook`;
    const params = new URLSearchParams({
      From: cleanTo,
      To: callerId,
      CallerId: callerId,
      Url: webhookUrl,
      StatusCallback: webhookUrl,
      CallType: 'trans',
      TimeLimit: '3600',
      TimeOut: '30'
    });

    const exotelRes = await fetch(exotelUrl, {
      method: 'POST',
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: params.toString()
    });

    const data = await exotelRes.json();
    console.log(`[Exotel Outbound Call] Triggered call to ${cleanTo} via Webhook ${webhookUrl}:`, data);
    res.json({ success: true, data });
  } catch (err) {
    console.error('[Exotel Outbound Call Error]:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;

